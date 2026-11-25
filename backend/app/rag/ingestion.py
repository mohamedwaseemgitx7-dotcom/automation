"""ZIP -> safe extract -> parse -> chunk -> local embeddings -> active knowledge base."""
import hashlib
import logging
import shutil
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select, update

from ..core import db
from ..core.config import get_settings
from ..llm.ollama_client import LocalModelError, Ollama
from . import chunking, parsers, zip_safe

log = logging.getLogger(__name__)

IMAGE_PROMPT = ("Describe this image for a business knowledge base. List visible products, brands, models, "
                "text, prices and labels exactly as shown. Do not guess anything that is not visible.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _set(kb_id: int, **fields) -> None:
    with db.session() as s:
        s.execute(update(db.KnowledgeBase).where(db.KnowledgeBase.id == kb_id).values(**fields))
        s.commit()


def process(kb_id: int, zip_path: Path, ollama: Ollama | None = None) -> None:
    st = get_settings()
    ollama = ollama or Ollama()
    dest = st.storage_dir / "extracted" / f"kb_{kb_id}"
    try:
        _set(kb_id, progress=5, message="checking archive")
        items = zip_safe.extract(zip_path, dest, st.max_files, st.max_unpacked_mb << 20, st.max_ratio)
    except zip_safe.ZipRejected as exc:
        _set(kb_id, status="failed", message=str(exc), progress=100)
        shutil.rmtree(dest, ignore_errors=True)
        return
    with db.session() as s:
        cfg = db.get_config(s)
        use_vision = cfg.image_understanding
        s.commit()

    texts: list[tuple[int, str, str, str]] = []   # (file_id, source, location, text)
    for n, it in enumerate(items, 1):
        _set(kb_id, progress=5 + int(60 * n / max(1, len(items))), message=f"reading {it.rel[:60]}")
        with db.session() as s:
            f = db.KnowledgeFile(kb_id=kb_id, path=it.rel, kind=it.kind, size=it.size)
            s.add(f)
            s.flush()
            fid = f.id
            try:
                if it.kind == "skipped":
                    f.status, f.error = "skipped", it.note
                elif it.kind == "document":
                    for loc, text in parsers.parse(it.path):
                        for c in chunking.chunk(text):
                            texts.append((fid, it.rel, loc, c))
                    f.status = "ok"
                elif it.kind == "image":
                    if not use_vision:
                        f.status, f.error = "skipped", "image understanding is off in AI settings"
                    else:
                        desc = ollama.chat("You describe images precisely.", IMAGE_PROMPT,
                                           model=st.vision_model, images=[it.path.read_bytes()], max_tokens=300)
                        texts.append((fid, it.rel, "image description", desc["text"]))
                        f.status = "ok"
                elif it.kind == "audio":
                    f.status, f.error = "skipped", "audio transcription arrives in Phase 3"
            except (LocalModelError, ValueError, OSError) as exc:
                f.status, f.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
            except Exception as exc:  # parser bugs on hostile files must not stop the whole ZIP
                f.status, f.error = "failed", f"{type(exc).__name__}"
            s.commit()

    if not texts:
        _set(kb_id, status="failed", progress=100, message="no readable text found in the ZIP")
        return
    _set(kb_id, progress=70, message=f"creating {len(texts)} embeddings locally")
    try:
        vecs = ollama.embed([t[3] for t in texts])
    except LocalModelError as exc:
        _set(kb_id, status="failed", progress=100, message=f"embedding model failed: {exc}")
        return
    with db.session() as s:
        counts: dict[int, int] = {}
        for (fid, src, loc, text), v in zip(texts, vecs):
            s.add(db.KnowledgeChunk(kb_id=kb_id, file_id=fid, source=src, location=loc, text=text,
                                    embedding=np.asarray(v, dtype=np.float32).tobytes()))
            counts[fid] = counts.get(fid, 0) + 1
        for fid, c in counts.items():
            s.execute(update(db.KnowledgeFile).where(db.KnowledgeFile.id == fid).values(chunks=c))
        # only one active knowledge base
        s.execute(update(db.KnowledgeBase).values(active=False))
        s.execute(update(db.KnowledgeBase).where(db.KnowledgeBase.id == kb_id)
                  .values(active=True, status="ready", progress=100, message=f"{len(texts)} chunks indexed"))
        db.audit(s, "system", "kb_ready", kb_id=kb_id, chunks=len(texts))
        s.commit()
    from .retrieval import invalidate
    invalidate()


def delete_kb(kb_id: int) -> None:
    st = get_settings()
    with db.session() as s:
        for model in (db.KnowledgeChunk, db.KnowledgeFile):
            s.execute(delete(model).where(model.kb_id == kb_id))
        s.execute(delete(db.KnowledgeBase).where(db.KnowledgeBase.id == kb_id))
        db.audit(s, "owner", "kb_deleted", kb_id=kb_id)
        s.commit()
    shutil.rmtree(st.storage_dir / "extracted" / f"kb_{kb_id}", ignore_errors=True)
    for p in (st.storage_dir / "uploads").glob(f"kb_{kb_id}_*"):
        p.unlink(missing_ok=True)
    from .retrieval import invalidate
    invalidate()


def active_kb_id() -> int | None:
    with db.session() as s:
        return s.scalar(select(db.KnowledgeBase.id).where(db.KnowledgeBase.active.is_(True)))
