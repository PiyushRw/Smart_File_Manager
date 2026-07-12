"""
ai_file — Intelligent File Organiser package.

Sub-modules
-----------
  extractor   Text extraction from diverse file formats.
  logic       FileOrganizer class (core pipeline).
  categorizer FileCategorizer class (rule-based type classification).
  config      AppConfig dataclass (settings management).
  utils       Logging setup, GPU detection, lazy model singletons.
  gui         Modern tkinter GUI.
"""

__version__ = "2.0.0"
__author__ = "ai_file contributors"

from .config import AppConfig
from .categorizer import FileCategorizer
from .extractor import extract_text, is_supported, validate_text
from .logic import FileOrganizer, extract_phrases
from .utils import setup_logging, is_cuda_available

__all__ = [
    "AppConfig",
    "FileCategorizer",
    "extract_text",
    "is_supported",
    "validate_text",
    "FileOrganizer",
    "extract_phrases",
    "setup_logging",
    "is_cuda_available",
]
