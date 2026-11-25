"""Text extraction from documents (data only - macros and scripts are never run)."""
import csv
from pathlib import Path


def parse(path: Path) -> list[tuple[str, str]]:
    """Return [(location, text)] sections."""
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return [("", path.read_text(encoding="utf-8", errors="replace"))]
    if ext == ".pdf":
        import pymupdf
        with pymupdf.open(path) as doc:
            return [(f"page {i + 1}", page.get_text()) for i, page in enumerate(doc)]
    if ext == ".docx":
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return [("", "\n".join(parts))]
    if ext == ".csv":
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.reader(f))
        return [("", _rows_to_text(rows))]
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)  # values only, formulas not evaluated
        out = []
        for ws in wb.worksheets:
            rows = [[("" if v is None else str(v)) for v in r] for r in ws.iter_rows(values_only=True)]
            out.append((f"sheet {ws.title}", _rows_to_text(rows)))
        wb.close()
        return out
    raise ValueError(f"unsupported document type {ext}")


def _rows_to_text(rows: list[list[str]]) -> str:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    header = rows[0]
    lines = []
    for r in rows[1:]:
        pairs = [f"{h.strip()}: {v.strip()}" for h, v in zip(header, r) if v.strip()]
        lines.append("; ".join(pairs))
    return "\n".join(lines) if lines else " | ".join(header)
