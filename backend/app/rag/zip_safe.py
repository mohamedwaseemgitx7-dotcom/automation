"""Safe ZIP extraction: size/count/ratio limits, no traversal, no links, no encrypted or executable entries."""
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DOCS = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO = {".wav", ".mp3", ".ogg", ".m4a", ".opus"}
BLOCKED = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".js", ".jse", ".wsf", ".msi", ".scr", ".com",
           ".sh", ".py", ".jar", ".docm", ".xlsm", ".pptm", ".dotm", ".hta", ".lnk", ".iso", ".apk", ".zip", ".rar",
           ".7z", ".gz", ".tar"}
MAGIC = {".pdf": [b"%PDF"], ".docx": [b"PK\x03\x04"], ".xlsx": [b"PK\x03\x04"], ".png": [b"\x89PNG"],
         ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"], ".webp": [b"RIFF"], ".ogg": [b"OggS"],
         ".opus": [b"OggS"], ".wav": [b"RIFF"], ".mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]}


class ZipRejected(ValueError):
    pass


@dataclass
class Extracted:
    rel: str
    path: Path
    kind: str      # document|image|audio|skipped
    size: int
    note: str = ""


def kind_of(name: str) -> str:
    ext = PurePosixPath(name).suffix.lower()
    if ext in DOCS:
        return "document"
    if ext in IMAGES:
        return "image"
    if ext in AUDIO:
        return "audio"
    return "skipped"


def _safe_rel(name: str) -> str:
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or any(part in ("..", "") for part in p.parts) or ":" in p.parts[0]:
        raise ZipRejected(f"unsafe path in archive: {name[:80]}")
    return p.as_posix()


def extract(zip_path: Path, dest: Path, max_files: int, max_unpacked: int, max_ratio: int) -> list[Extracted]:
    if not zipfile.is_zipfile(zip_path):
        raise ZipRejected("not a ZIP file")
    out: list[Extracted] = []
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_files:
            raise ZipRejected(f"too many files ({len(infos)} > {max_files})")
        total = sum(i.file_size for i in infos)
        if total > max_unpacked:
            raise ZipRejected("archive unpacks to more than the allowed size")
        packed = max(1, sum(i.compress_size for i in infos))
        if total / packed > max_ratio:
            raise ZipRejected("compression ratio too high (possible zip bomb)")
        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()
        for info in infos:
            rel = _safe_rel(info.filename)
            if info.flag_bits & 0x1:
                raise ZipRejected("encrypted archives are not supported")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ZipRejected(f"symbolic link in archive: {rel[:80]}")
            name = PurePosixPath(rel).name
            if name.startswith(".") or "__MACOSX" in rel:
                continue
            ext = PurePosixPath(rel).suffix.lower()
            if ext in BLOCKED:
                out.append(Extracted(rel, Path(), "skipped", info.file_size, "blocked file type (never executed)"))
                continue
            kind = kind_of(rel)
            if kind == "skipped":
                out.append(Extracted(rel, Path(), "skipped", info.file_size, "unsupported type"))
                continue
            target = (root / rel).resolve()
            if root not in target.parents:
                raise ZipRejected(f"path escapes target folder: {rel[:80]}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                written = 0
                while chunk := src.read(1 << 16):
                    written += len(chunk)
                    if written > info.file_size + 1024:
                        raise ZipRejected("entry larger than declared size")
                    dst.write(chunk)
            head = target.read_bytes()[:8]
            if ext in MAGIC and not any(head.startswith(m) for m in MAGIC[ext]):
                target.unlink()
                out.append(Extracted(rel, Path(), "skipped", info.file_size, "content does not match file type"))
                continue
            out.append(Extracted(rel, target, kind, info.file_size))
    return out
