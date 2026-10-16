"""
Sinfonia — File Reader
Estrae testo da PDF, DOCX, XLSX, immagini (OCR), TXT, CSV, MD, JSON.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

log = structlog.get_logger()

MAX_TEXT_LENGTH = 4000  # caratteri massimi restituiti


@dataclass
class FileContent:
    filename: str
    filetype: str
    text: str
    size_bytes: int
    pages: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "filetype": self.filetype,
            "text": self.text,
            "size_bytes": self.size_bytes,
            "pages": self.pages,
            "error": self.error,
        }


def detect_filetype(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext or "unknown"


def _read_pdf(path: Path) -> tuple[str, int | None]:
    """Legge PDF con pdfplumber (testo + tabelle)."""
    import pdfplumber
    text_parts = []
    pages = 0
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"[Pagina {i+1}]\n{page_text}")
    return "\n\n".join(text_parts), pages


def _read_docx(path: Path) -> tuple[str, None]:
    """Legge DOCX con python-docx."""
    from docx import Document
    doc = Document(str(path))
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    # Leggi anche le tabelle
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            parts.append("[Tabella]\n" + "\n".join(rows))
    return "\n\n".join(parts), None


def _read_xlsx(path: Path) -> tuple[str, None]:
    """Legge XLSX con openpyxl."""
    import openpyxl
    wb = openpyxl.load_workbook(str(path), data_only=True)
    parts = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        parts.append(f"[Foglio: {sheet_name}]")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts), None


def _read_image(path: Path) -> tuple[str, None]:
    """Estrae testo da immagine con Tesseract OCR."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", None

    # Verifica Tesseract
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return "[OCR non disponibile: Tesseract non installato]", None

    img = Image.open(path)
    # Prova italiano + inglese
    try:
        text = pytesseract.image_to_string(img, lang="ita+eng")
    except Exception:
        text = pytesseract.image_to_string(img, lang="eng")
    return text, None


def _read_text(path: Path) -> tuple[str, None]:
    """Legge file di testo."""
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1"), None


READERS = {
    "pdf": _read_pdf,
    "docx": _read_docx,
    "doc": _read_docx,
    "xlsx": _read_xlsx,
    "xls": _read_xlsx,
    "png": _read_image,
    "jpg": _read_image,
    "jpeg": _read_image,
    "gif": _read_image,
    "bmp": _read_image,
    "webp": _read_image,
    "txt": _read_text,
    "md": _read_text,
    "csv": _read_text,
    "json": _read_text,
    "log": _read_text,
}


def read_file_bytes(filename: str, data: bytes) -> FileContent:
    """Estrae testo da un file in bytes."""
    filetype = detect_filetype(filename)
    size = len(data)

    reader = READERS.get(filetype)
    if not reader:
        return FileContent(
            filename=filename,
            filetype=filetype,
            text="",
            size_bytes=size,
            error=f"Tipo di file non supportato: .{filetype}",
        )

    # Scrivi in file temporaneo (molti reader vogliono un path)
    suffix = f".{filetype}" if filetype != "unknown" else ""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp_path = Path(f.name)

    try:
        text, pages = reader(tmp_path)
    except Exception as e:
        log.error("file_reader.error", filename=filename, error=str(e))
        return FileContent(
            filename=filename,
            filetype=filetype,
            text="",
            size_bytes=size,
            error=f"Errore lettura: {str(e)[:200]}",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # Tronca se troppo lungo
    truncated = False
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        truncated = True

    if truncated:
        text += f"\n\n[... testo troncato a {MAX_TEXT_LENGTH} caratteri ...]"

    log.info(
        "file_reader.read_ok",
        filename=filename,
        filetype=filetype,
        chars=len(text),
        pages=pages,
    )

    return FileContent(
        filename=filename,
        filetype=filetype,
        text=text,
        size_bytes=size,
        pages=pages,
    )


if __name__ == "__main__":
    # Test rapido
    print("=== File Reader — test ===")
    test_txt = "Ciao, questo è un test.".encode("utf-8")
    result = read_file_bytes("test.txt", test_txt)
    print(f"TXT: {result.text!r}")
    print(f"File supportati: {sorted(READERS.keys())}")
