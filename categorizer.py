"""
categorizer.py — Rule-based file-type categorisation for ai_file.

``FileCategorizer`` maps file extensions to user-configurable category names
and can generate a destination preview without moving any files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from .config import AppConfig

logger = logging.getLogger("ai_file.categorizer")


class FileCategorizer:
    """
    Maps file extensions to category names using the rules in ``AppConfig``.

    After instantiation, call :meth:`refresh` whenever the config's
    ``categories`` or ``excluded_extensions`` change.

    Example
    -------
    >>> cat = FileCategorizer(config)
    >>> cat.get_category("/home/user/report.pdf")
    'Documents'
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._ext_to_category: Dict[str, str] = {}
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the internal extension→category lookup table."""
        mapping: Dict[str, str] = {}
        for category, extensions in self._config.categories.items():
            for ext in extensions:
                mapping[ext.lower()] = category
        self._ext_to_category = mapping
        logger.debug(
            "Category map rebuilt: %d categories, %d extensions.",
            len(self._config.categories),
            len(mapping),
        )

    def get_category(self, file_path: str | Path) -> str:
        """
        Return the category name for *file_path*.

        Returns ``"Excluded"`` for extensions in ``config.excluded_extensions``
        and ``"Misc"`` for unrecognised extensions.
        """
        ext = Path(file_path).suffix.lower()
        if ext in self._config.excluded_extensions:
            return "Excluded"
        return self._ext_to_category.get(ext, "Misc")

    def preview_structure(
        self,
        file_paths: List[str | Path],
        destination: str | Path,
    ) -> Dict[str, List[str]]:
        """
        Return the projected folder structure without touching any files.

        Parameters
        ----------
        file_paths:
            List of source file paths to preview.
        destination:
            The output root folder.

        Returns
        -------
        Dict[str, List[str]]
            Mapping of ``category → [absolute destination path, …]``.
        """
        destination = Path(destination)
        structure: Dict[str, List[str]] = {}
        for fp in file_paths:
            fp = Path(fp)
            cat = self.get_category(fp)
            dest = str(destination / cat / fp.name)
            structure.setdefault(cat, []).append(dest)
        return structure

    # ------------------------------------------------------------------
    # Category management
    # ------------------------------------------------------------------

    @property
    def categories(self) -> Dict[str, List[str]]:
        """Reference to the live category dict from the config."""
        return self._config.categories

    def add_category(self, name: str, extensions: List[str]) -> None:
        """Add a new category (or replace an existing one) and refresh the map."""
        self._config.categories[name] = [e.lower() for e in extensions]
        self.refresh()
        logger.info("Category added/updated: '%s' (%d exts)", name, len(extensions))

    def remove_category(self, name: str) -> None:
        """Remove a category by name and refresh the map."""
        if name in self._config.categories:
            del self._config.categories[name]
            self.refresh()
            logger.info("Category removed: '%s'", name)

    def update_extensions(self, category: str, extensions: List[str]) -> None:
        """Replace the extension list for an existing category."""
        if category not in self._config.categories:
            logger.warning("Category '%s' not found — use add_category().", category)
            return
        self._config.categories[category] = [e.lower() for e in extensions]
        self.refresh()

    def all_known_extensions(self) -> List[str]:
        """Return a sorted list of all extensions currently in the category map."""
        return sorted(self._ext_to_category.keys())
