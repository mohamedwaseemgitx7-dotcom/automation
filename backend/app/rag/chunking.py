"""Split text into overlapping chunks on paragraph / sentence boundaries."""
import re

TARGET_WORDS = 180
OVERLAP_WORDS = 30


def chunk(text: str, target: int = TARGET_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[-*•#\d])", text) if p.strip()]
    units: list[str] = []
    for p in paras:  # break very long paragraphs into sentences
        if len(p.split()) > target:
            units.extend(s for s in re.split(r"(?<=[.!?])\s+", p) if s)
        else:
            units.append(p)
    chunks, cur = [], []
    for u in units:
        if cur and sum(len(x.split()) for x in cur) + len(u.split()) > target:
            chunks.append("\n".join(cur))
            tail = " ".join(" ".join(cur).split()[-overlap:])
            cur = [tail] if overlap else []
        cur.append(u)
    if cur:
        chunks.append("\n".join(cur))
    # hard split of anything still too long
    out = []
    for c in chunks:
        w = c.split()
        for i in range(0, len(w), target * 2):
            out.append(" ".join(w[i:i + target * 2]))
    return [c for c in out if len(c.split()) >= 3]
