"""
Smart File Manager — Intelligent File Organiser package.

Sub-modules
-----------
  extractor   Text extraction from diverse file formats.
  logic       FileOrganizer class (core pipeline).
  categorizer FileCategorizer class (rule-based type classification).
  config      AppConfig dataclass (settings management).
  utils       Logging setup, GPU detection, lazy model singletons.
  gui         Modern tkinter GUI.

Usage
-----
  Run directly:
      python run.py                     # GUI mode
      python run.py --cli --source ...  # CLI mode

  The folder name contains spaces so standard ``import`` syntax cannot be used.
  Always run via ``run.py`` which sets up sys.path automatically.
"""

__version__ = "2.0.0"
__author__  = "Smart File Manager contributors"

# ---------------------------------------------------------------------------
# Conditional imports — work whether this file is loaded as part of a package
# (relative imports) or the modules are on sys.path directly (absolute).
# ---------------------------------------------------------------------------
try:
    # Package mode: folder accessible as a proper Python package
    from .config     import AppConfig
    from .categorizer import FileCategorizer
    from .extractor  import extract_text, is_supported, validate_text
    from .logic      import FileOrganizer, extract_phrases, build_match_text
    from .utils      import setup_logging, is_cuda_available
except ImportError:
    # Direct-run mode: modules are on sys.path individually
    from config      import AppConfig          # type: ignore[no-redef]
    from categorizer import FileCategorizer    # type: ignore[no-redef]
    from extractor   import extract_text, is_supported, validate_text   # type: ignore[no-redef]
    from logic       import FileOrganizer, extract_phrases, build_match_text  # type: ignore[no-redef]
    from utils       import setup_logging, is_cuda_available  # type: ignore[no-redef]

__all__ = [
    "AppConfig",
    "FileCategorizer",
    "extract_text",
    "is_supported",
    "validate_text",
    "FileOrganizer",
    "extract_phrases",
    "build_match_text",
    "setup_logging",
    "is_cuda_available",
]
