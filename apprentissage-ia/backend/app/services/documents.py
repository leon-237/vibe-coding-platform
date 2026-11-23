"""Text extraction and chunking for uploaded course files (PDF, DOCX, TXT, MD)."""
from __future__ import annotations

import io
import re
from pathlib import PurePath

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedFile(Exception):
    pass


class EmptyDocument(Exception):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFile(f"Format non pris en charge : {ext or 'inconnu'}")
    try:
        if ext == ".pdf":
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext == ".docx":
            document = DocxDocument(io.BytesIO(data))
            text = "\n".join(p.text for p in document.paragraphs)
        else:
            text = data.decode("utf-8", errors="replace")
    except Exception as exc:  # corrupt files raise many library-specific errors
        raise UnsupportedFile("Fichier illisible") from exc
    text = text.strip()
    if not text:
        raise EmptyDocument("Aucun texte exploitable (PDF scanné ? une version texte est nécessaire)")
    return text


def chunk_text(text: str, size: int = 1200, overlap: int = 120) -> list[str]:
    """Split on paragraphs, packing them up to `size` characters with a small overlap."""
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", text)]
    paragraphs = [p for p in paragraphs if p]

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > size:  # very long paragraph: hard split
            head, paragraph = paragraph[:size], paragraph[size - overlap :]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if len(current) + len(paragraph) + 1 > size and current:
            chunks.append(current)
            current = current[-overlap:] + " " + paragraph
        else:
            current = f"{current} {paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks
