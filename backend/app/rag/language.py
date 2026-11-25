"""Very small language detector: Tamil script, Malay markers, else English."""
from .normalize import MALAY_MARKERS, tokens


def detect(text: str) -> str:
    if any("஀" <= ch <= "௿" for ch in text or ""):
        return "ta"
    words = tokens(text)
    if not words:
        return "en"
    hits = sum(1 for w in words if w in MALAY_MARKERS)
    return "ms" if hits >= max(1, len(words) // 4) else "en"
