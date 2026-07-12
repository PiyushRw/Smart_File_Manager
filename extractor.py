"""
extractor.py — Extract plain text from a wide variety of file formats.

Supported formats
-----------------
  PDF (.pdf)          — pdfplumber text layer, EasyOCR fallback for scanned pages
  Word (.docx)        — python-docx
  PowerPoint (.pptx)  — python-pptx
  Excel (.xlsx/.xls)  — pandas / openpyxl
  CSV (.csv)          — pandas
  Plain text (.txt)   — UTF-8 read
  Markdown (.md)      — UTF-8 read
  HTML (.html/.htm)   — BeautifulSoup
  XML (.xml)          — xml.etree.ElementTree
  JSON (.json)        — json.dumps pretty-print
  Email (.eml)        — email stdlib
  Images              — EasyOCR  (.png .jpg .jpeg .bmp .webp .tiff)
  Audio               — faster-whisper  (.mp3 .wav .m4a .flac .ogg)
  Video               — moviepy → temp WAV → faster-whisper  (.mp4 .avi .mov .mkv .wmv)

GPU acceleration
----------------
  EasyOCR uses CUDA when available (via ``utils.get_ocr_reader()``).
  Whisper uses CUDA float16 when available (via ``utils.get_whisper_model()``).
  Both fall back to CPU silently if no CUDA GPU is detected.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Callable, Dict, Optional

from bs4 import BeautifulSoup          # type: ignore
from docx import Document              # type: ignore
from pptx import Presentation          # type: ignore
import pandas as pd
import pdfplumber                      # type: ignore
# moviepy is imported lazily inside _extract_video() to support both
# 1.x (moviepy.editor) and 2.x (moviepy / moviepy.video.io) import paths.

from .utils import get_ocr_reader, get_whisper_model

logger = logging.getLogger("ai_file.extractor")

# ---------------------------------------------------------------------------
# Dispatch table  —  extension → internal handler name
# ---------------------------------------------------------------------------

_SUPPORTED: Dict[str, str] = {
    # Documents
    ".pdf":  "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "excel",
    ".xls":  "excel",
    ".csv":  "csv",
    ".txt":  "txt",
    ".md":   "markdown",
    # Web / structured data
    ".html": "html",
    ".htm":  "html",
    ".xml":  "xml",
    ".json": "json_",
    # Email
    ".eml":  "email_",
    # Images (OCR)
    ".png":  "image",
    ".jpg":  "image",
    ".jpeg": "image",
    ".bmp":  "image",
    ".webp": "image",
    ".tiff": "image",
    ".tif":  "image",
    # Audio (transcription)
    ".mp3":  "audio",
    ".wav":  "audio",
    ".m4a":  "audio",
    ".flac": "audio",
    ".ogg":  "audio",
    # Video (audio-track → transcription)
    ".mp4":  "video",
    ".avi":  "video",
    ".mov":  "video",
    ".mkv":  "video",
    ".wmv":  "video",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text(
    file_path: str | Path,
    whisper_model_size: str = "base",
) -> str:
    """
    Extract plain text from *file_path*.

    Parameters
    ----------
    file_path:
        Absolute or relative path to the source file.
    whisper_model_size:
        Whisper model variant to use for audio/video transcription.

    Returns
    -------
    str
        Extracted text (may be an empty string for blank/silent files).

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist on disk.
    ValueError
        If the file extension is not in the supported set.
    RuntimeError
        If a handler raises an unexpected error (re-raised with context).
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = file_path.suffix.lower()
    handler_key = _SUPPORTED.get(ext)
    if handler_key is None:
        raise ValueError(
            f"Unsupported file type: {ext!r}.  "
            f"Supported: {sorted(_SUPPORTED.keys())}"
        )

    handler: Optional[Callable] = _HANDLERS.get(handler_key)
    if handler is None:
        raise RuntimeError(f"No handler registered for key '{handler_key}'.")  # pragma: no cover

    logger.debug("Extracting from %s (handler=%s)", file_path.name, handler_key)
    try:
        text = handler(file_path)
    except Exception as exc:
        logger.error("Extraction failed for '%s': %s", file_path.name, exc, exc_info=True)
        raise RuntimeError(f"Could not extract text from '{file_path.name}': {exc}") from exc

    return text or ""


def is_supported(file_path: str | Path) -> bool:
    """Return ``True`` if *file_path* has a supported extension."""
    return Path(file_path).suffix.lower() in _SUPPORTED


def validate_text(
    text: str,
    min_words: int = 5,
    strict: bool = False,
) -> str:
    """
    Validate extracted text meets a minimum word-count threshold.

    Parameters
    ----------
    text:
        The extracted text string.
    min_words:
        Minimum acceptable word count.
    strict:
        If ``True``, raise ``ValueError`` when below threshold; otherwise log
        a warning and return the text unchanged.

    Returns
    -------
    str
        The original *text* (possibly with a warning logged).
    """
    if not text or not text.strip():
        msg = "No text could be extracted."
        if strict:
            raise ValueError(msg)
        logger.warning(msg)
        return text

    word_count = len(text.split())
    if word_count < min_words:
        msg = (
            f"Extracted text has only {word_count} words "
            f"(minimum={min_words})."
        )
        if strict:
            raise ValueError(msg)
        logger.warning(msg)

    return text


# ---------------------------------------------------------------------------
# Private handler implementations
# ---------------------------------------------------------------------------

def _extract_pdf(file_path: Path) -> str:
    """
    Extract text from a PDF using pdfplumber.

    For pages that yield no embedded text (scanned pages), EasyOCR is used
    as a fallback.  OCR errors on individual pages are logged but do not
    abort extraction of the rest of the document.
    """
    all_text: list[str] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()

            if text:
                all_text.append(text)
            else:
                # Scanned / image-only page — fall back to OCR
                logger.debug(
                    "Page %d of '%s' has no text layer — running OCR.",
                    page_num, file_path.name,
                )
                try:
                    import numpy as np  # type: ignore

                    pil_image = page.to_image(resolution=200).original
                    reader = get_ocr_reader()
                    results = reader.readtext(np.array(pil_image))
                    ocr_text = " ".join(item[1] for item in results).strip()
                    if ocr_text:
                        all_text.append(ocr_text)
                except Exception as exc:
                    logger.warning(
                        "OCR failed on page %d of '%s': %s",
                        page_num, file_path.name, exc,
                    )

    return "\n\n".join(all_text)


def _extract_docx(file_path: Path) -> str:
    doc = Document(file_path)
    return "\n".join(
        para.text for para in doc.paragraphs if para.text.strip()
    )


def _extract_pptx(file_path: Path) -> str:
    prs = Presentation(file_path)
    parts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                parts.append(shape.text.strip())
    return "\n".join(parts)


def _extract_excel(file_path: Path) -> str:
    sheets = pd.read_excel(file_path, sheet_name=None)
    parts: list[str] = []
    for sheet_name, df in sheets.items():
        parts.append(f"=== Sheet: {sheet_name} ===")
        parts.append(df.to_string(index=False))
    return "\n".join(parts)


def _extract_csv(file_path: Path) -> str:
    df = pd.read_csv(file_path)
    return df.to_string(index=False)


def _extract_txt(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="replace")


def _extract_markdown(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="replace")


def _extract_html(file_path: Path) -> str:
    html = file_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")


def _extract_xml(file_path: Path) -> str:
    tree = ET.parse(file_path)
    root = tree.getroot()
    parts: list[str] = []
    for node in root.iter():
        if node.text and node.text.strip():
            parts.append(node.text.strip())
    return "\n".join(parts)


def _extract_json_(file_path: Path) -> str:
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return json.dumps(data, indent=2, ensure_ascii=False)


def _extract_image(file_path: Path) -> str:
    reader = get_ocr_reader()
    results = reader.readtext(str(file_path))
    return " ".join(item[1] for item in results).strip()


def _extract_audio(file_path: Path) -> str:
    model = get_whisper_model()
    segments, _ = model.transcribe(str(file_path))
    return " ".join(seg.text for seg in segments).strip()



def _get_video_file_clip():
    """
    Return ``VideoFileClip`` class, trying all known moviepy import paths.

    moviepy 2.x (≥2.0):  ``from moviepy import VideoFileClip``
                           or ``from moviepy.video.io.VideoFileClip import VideoFileClip``
    moviepy 1.x:          ``from moviepy.editor import VideoFileClip``
    """
    # Try moviepy 2.x top-level first (works in some 2.x builds)
    try:
        from moviepy import VideoFileClip  # type: ignore
        return VideoFileClip
    except ImportError:
        pass

    # Try moviepy 2.x submodule path
    try:
        from moviepy.video.io.VideoFileClip import VideoFileClip  # type: ignore
        return VideoFileClip
    except ImportError:
        pass

    # Fall back to moviepy 1.x
    try:
        from moviepy.editor import VideoFileClip  # type: ignore
        return VideoFileClip
    except ImportError:
        pass

    raise ImportError(
        "Could not import VideoFileClip from moviepy. "
        "Install moviepy with: pip install moviepy"
    )


def _extract_video(file_path: Path) -> str:
    """
    Extract the audio track from a video file and transcribe it.

    Supports moviepy 1.x and 2.x import paths automatically.
    A temporary WAV file is written to disk, transcribed, and always
    deleted in the ``finally`` block to prevent temp-file leaks.
    """
    # Lazy import — handles moviepy 1.x and 2.x API differences
    VideoFileClip = _get_video_file_clip()

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        video = VideoFileClip(str(file_path))
        try:
            if video.audio is None:
                logger.warning("Video '%s' has no audio track.", file_path.name)
                return ""
            video.audio.write_audiofile(tmp_path, logger=None)
        finally:
            video.close()

        return _extract_audio(Path(tmp_path))

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                logger.warning("Could not delete temp file '%s': %s", tmp_path, exc)


def _extract_email_(file_path: Path) -> str:
    with open(file_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    parts.append(part.get_content())
                except Exception as exc:
                    logger.debug("Skipping MIME part: %s", exc)
    else:
        try:
            parts.append(msg.get_content())
        except Exception as exc:
            logger.warning("Could not read email content: %s", exc)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Handler dispatch table  (populated after function definitions)
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, Callable] = {
    "pdf":      _extract_pdf,
    "docx":     _extract_docx,
    "pptx":     _extract_pptx,
    "excel":    _extract_excel,
    "csv":      _extract_csv,
    "txt":      _extract_txt,
    "markdown": _extract_markdown,
    "html":     _extract_html,
    "xml":      _extract_xml,
    "json_":    _extract_json_,
    "email_":   _extract_email_,
    "image":    _extract_image,
    "audio":    _extract_audio,
    "video":    _extract_video,
}