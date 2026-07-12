"""
utils.py — Shared utilities for ai_file.

Provides:
  - Logging setup (console + optional file handler).
  - GPU detection via PyTorch.
  - Thread-safe lazy singletons for heavy ML models (Whisper, EasyOCR,
    SentenceTransformer) so they are initialized on first use, not at
    import time.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_file: Optional[str] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configure the root logger.

    Parameters
    ----------
    log_file:
        Optional path for a file log handler.
    level:
        Logging verbosity level (e.g. ``logging.DEBUG``).

    Returns
    -------
    logging.Logger
        The ``ai_file`` package logger.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("ai_file")


logger = logging.getLogger("ai_file")

# ---------------------------------------------------------------------------
# GPU Detection
# ---------------------------------------------------------------------------

_cuda_available: Optional[bool] = None


def is_cuda_available() -> bool:
    """
    Return ``True`` if a CUDA-capable GPU is available via PyTorch.

    The result is cached after the first call. Falls back to ``False``
    if PyTorch is not installed.
    """
    global _cuda_available
    if _cuda_available is None:
        try:
            import torch  # type: ignore

            _cuda_available = torch.cuda.is_available()
            if _cuda_available:
                logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
            else:
                logger.info("No CUDA GPU detected — using CPU.")
        except ImportError:
            _cuda_available = False
            logger.warning("PyTorch not installed; GPU acceleration unavailable.")
    return _cuda_available


# ---------------------------------------------------------------------------
# Lazy model singletons (thread-safe double-checked locking)
# ---------------------------------------------------------------------------

# ---- Whisper ---------------------------------------------------------------

_whisper_lock = threading.Lock()
_whisper_model = None
_whisper_model_size: str = "base"


def get_whisper_model(model_size: str = "base"):
    """
    Return a cached ``WhisperModel``, initializing on first call.

    GPU (CUDA float16) is used when available; otherwise CPU int8.

    Parameters
    ----------
    model_size:
        One of ``"tiny"``, ``"base"``, ``"small"``, ``"medium"``, ``"large"``.
    """
    global _whisper_model, _whisper_model_size

    if _whisper_model is None or _whisper_model_size != model_size:
        with _whisper_lock:
            if _whisper_model is None or _whisper_model_size != model_size:
                from faster_whisper import WhisperModel  # type: ignore

                device = "cuda" if is_cuda_available() else "cpu"
                compute = "float16" if device == "cuda" else "int8"
                logger.info(
                    "Loading Whisper model '%s' on %s (compute=%s) …",
                    model_size,
                    device,
                    compute,
                )
                _whisper_model = WhisperModel(
                    model_size, device=device, compute_type=compute
                )
                _whisper_model_size = model_size
                logger.info("Whisper model ready.")

    return _whisper_model


# ---- EasyOCR ---------------------------------------------------------------

_ocr_lock = threading.Lock()
_ocr_reader = None


def get_ocr_reader(languages: Optional[List[str]] = None):
    """
    Return a cached ``easyocr.Reader``, initializing on first call.

    Uses CUDA if available.

    Parameters
    ----------
    languages:
        List of language codes (default ``["en"]``).
    """
    global _ocr_reader
    if _ocr_reader is None:
        with _ocr_lock:
            if _ocr_reader is None:
                import easyocr  # type: ignore

                langs = languages or ["en"]
                gpu = is_cuda_available()
                logger.info("Loading EasyOCR (langs=%s, gpu=%s) …", langs, gpu)
                _ocr_reader = easyocr.Reader(langs, gpu=gpu)
                logger.info("EasyOCR ready.")
    return _ocr_reader


# ---- SentenceTransformer ---------------------------------------------------

_st_lock = threading.Lock()
_st_model = None
_st_model_name: str = ""


def get_sentence_model(model_name: str = "all-MiniLM-L6-v2"):
    """
    Return a cached ``SentenceTransformer`` model, initializing on first call.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier (default ``"all-MiniLM-L6-v2"``).
    """
    global _st_model, _st_model_name

    if _st_model is None or _st_model_name != model_name:
        with _st_lock:
            if _st_model is None or _st_model_name != model_name:
                from sentence_transformers import SentenceTransformer  # type: ignore

                logger.info("Loading SentenceTransformer '%s' …", model_name)
                _st_model = SentenceTransformer(model_name)
                _st_model_name = model_name
                logger.info("SentenceTransformer ready.")

    return _st_model
