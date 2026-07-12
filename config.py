"""
config.py — Application configuration management for ai_file.

Provides an ``AppConfig`` dataclass that:
  - Holds all user-tunable settings.
  - Loads from / saves to a JSON file.
  - Supports import/export of configuration profiles.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("ai_file.config")

# ---------------------------------------------------------------------------
# Default extension → category mapping
# ---------------------------------------------------------------------------

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "Documents": [
        ".pdf", ".docx", ".doc", ".txt", ".odt", ".rtf", ".md", ".tex", ".pages",
    ],
    "Spreadsheets": [".xlsx", ".xls", ".csv", ".ods", ".numbers"],
    "Presentations": [".pptx", ".ppt", ".odp", ".key"],
    "Images": [
        ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
        ".tiff", ".tif", ".svg", ".ico", ".heic", ".raw",
    ],
    "Videos": [
        ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv",
        ".webm", ".m4v", ".3gp", ".ts",
    ],
    "Audio": [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus"],
    "Archives": [".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".zst"],
    "Code": [
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp",
        ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".r",
        ".m", ".sh", ".bat", ".ps1", ".lua", ".pl", ".scala",
    ],
    "Executables": [".exe", ".msi", ".app", ".deb", ".rpm", ".dmg", ".apk", ".bin"],
    "Web": [".html", ".htm", ".xml", ".json", ".yaml", ".yml", ".css", ".toml"],
    "Email": [".eml", ".msg"],
    "Databases": [".sql", ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
}

# Default location: inside the ai_file package directory
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"
_DEFAULT_DB_PATH = str(Path(__file__).parent / "file_registry.pkl")


@dataclass
class AppConfig:
    """
    All user-configurable settings for ai_file.

    Serialized to/from ``config.json`` in the project root.
    """

    # ---- Paths ------------------------------------------------------------
    scan_folders: List[str] = field(default_factory=list)
    """Source folders to scan for files."""

    output_folder: str = ""
    """Destination root folder where organised files land."""

    db_path: str = _DEFAULT_DB_PATH
    """Path to the pickle file used as the file registry / database."""

    # ---- Scan options -----------------------------------------------------
    recursive: bool = True
    """Recurse into sub-folders when scanning."""

    enable_categorization: bool = True
    """Automatically sort files into category sub-folders."""

    categories: Dict[str, List[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_CATEGORIES.items()}
    )
    """Extension → category mapping (user-editable)."""

    excluded_extensions: List[str] = field(default_factory=list)
    """Extensions to skip entirely (e.g. ``[".tmp", ".log"]``)."""

    selected_categories: List[str] = field(default_factory=list)
    """
    Categories to include in processing.
    Empty list = ALL categories are processed.
    Non-empty = only the listed category names are processed; others are skipped.
    """

    # ---- File action ------------------------------------------------------
    copy_then_delete: bool = True
    """
    Safe move strategy:
    copy to destination → verify → delete original.
    Set to ``False`` to use shutil.move() directly (faster but less safe).
    """

    preserve_structure: bool = False
    """Mirror the original sub-folder structure inside each category folder."""

    # ---- NLP --------------------------------------------------------------
    sentence_model: str = "all-MiniLM-L6-v2"
    """HuggingFace SentenceTransformer model name."""

    similarity_threshold: float = 0.45
    """Minimum cosine similarity (0-1) to assign a file to a query keyword folder."""

    min_word_count: int = 5
    """Minimum words in extracted text before a warning is emitted."""

    # ---- Whisper ----------------------------------------------------------
    whisper_model_size: str = "base"
    """Whisper model size for audio/video transcription."""

    # ---- GPU --------------------------------------------------------------
    use_gpu: bool = True
    """Attempt to use CUDA GPU for OCR and transcription."""

    # ---- UI ---------------------------------------------------------------
    theme: str = "dark"
    """GUI colour theme: ``"dark"`` or ``"light"``."""

    max_log_lines: int = 2000
    """Maximum number of lines retained in the live log panel."""

    # ---- Parallelism ------------------------------------------------------
    max_workers: int = 4
    """Number of parallel worker threads for file processing."""

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Resolve a bare/relative db_path to an absolute path inside ai_file/."""
        p = Path(self.db_path)
        if not p.is_absolute():
            self.db_path = str(Path(__file__).parent / p.name)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path = _DEFAULT_CONFIG_PATH) -> "AppConfig":
        """
        Load configuration from a JSON file.

        Falls back to defaults if the file is missing or corrupted.
        """
        path = Path(path)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                valid_keys = cls.__dataclass_fields__.keys()
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                return cls(**filtered)
            except Exception as exc:
                logger.warning(
                    "Could not load config from %s: %s — using defaults.", path, exc
                )
        return cls()

    def save(self, path: str | Path = _DEFAULT_CONFIG_PATH) -> None:
        """Persist the current configuration to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
        logger.debug("Config saved to %s", path)

    def export_profile(self, path: str | Path) -> None:
        """Export this configuration as a portable JSON profile."""
        self.save(path)

    @classmethod
    def import_profile(cls, path: str | Path) -> "AppConfig":
        """Import a configuration profile from a JSON file."""
        return cls.load(path)

    def reset_to_defaults(self) -> None:
        """Reset all fields to their factory defaults in-place."""
        defaults = AppConfig()
        for f_name in self.__dataclass_fields__:
            setattr(self, f_name, getattr(defaults, f_name))
