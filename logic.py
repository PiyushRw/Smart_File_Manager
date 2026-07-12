"""
logic.py — Core file-organiser pipeline for ai_file.

``FileOrganizer`` orchestrates the full workflow:
  1. Scan source folders for supported files.
  2. Extract text content from each file.
  3. Extract noun-phrase keywords from the text using spaCy.
  4. Compute semantic similarity against the user's query keywords using
     SentenceTransformer embeddings.
  5. Determine the destination folder (category + optional keyword sub-folder).
  6. Safely move the file: copy → verify → delete original.
  7. Record the action in a persistent Pandas DataFrame registry.

Parallel processing
-------------------
  File extraction + classification runs in a ``ThreadPoolExecutor`` (I/O-bound
  work benefits from threading in CPython; GIL is released during file I/O
  and by native extensions such as torch and easyocr).

Safe move strategy (copy-then-delete)
--------------------------------------
  ``safe_copy_then_delete()`` uses ``shutil.copy2`` (preserves metadata) and
  verifies the destination file size before removing the source.  If
  verification fails, the partial copy is deleted and the source is preserved.

Pause / Resume / Cancel
-----------------------
  The organiser checks ``threading.Event`` objects between file-processing
  futures so the GUI can pause, resume, or cancel a live run without killing
  worker threads mid-write.
"""

from __future__ import annotations

import logging
import os
import pickle
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import numpy as np
import pandas as pd
import spacy                                    # type: ignore
from sklearn.metrics.pairwise import cosine_similarity

from .config import AppConfig
from .categorizer import FileCategorizer
from .extractor import extract_text, is_supported, validate_text
from .utils import get_sentence_model

logger = logging.getLogger("ai_file.logic")

# Words to strip from user queries — action verbs, prepositions, function words.
# Only true nouns/noun phrases should survive as keyword folder names.
QUERY_ACTION_WORDS: Set[str] = {
    "organise", "organize", "sort", "match", "find", "search", "locate",
    "move", "copy", "transfer", "put", "place", "arrange", "group",
    "categorize", "categorise", "filter", "select", "show", "list",
    "get", "make", "create", "do", "use", "want", "need", "help",
    "please", "check", "scan", "process", "run", "start", "begin",
    "go", "take", "give", "look", "manage", "handle", "detect",
    "index", "rename", "delete", "remove", "all", "my", "the",
    "file", "files", "folder", "folders", "document", "documents",
}

# ---------------------------------------------------------------------------
# spaCy — loaded lazily to avoid blocking on import
# ---------------------------------------------------------------------------

_nlp: Optional[object] = None
_nlp_lock = threading.Lock()


def _get_nlp():
    global _nlp
    if _nlp is None:
        with _nlp_lock:
            if _nlp is None:
                logger.info("Loading spaCy model 'en_core_web_sm' …")
                _nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy ready.")
    return _nlp


# ---------------------------------------------------------------------------
# NLP helpers
# ---------------------------------------------------------------------------

def extract_phrases(text: str, nouns_only: bool = False) -> List[str]:
    """
    Extract meaningful noun-phrase keyword strings from *text*.

    Uses spaCy noun chunks, filters determiners/pronouns, and deduplicates.

    Parameters
    ----------
    text:
        Any plain-text string (capped to 100 000 chars).
    nouns_only:
        If ``True``, apply strict filtering suitable for query keyword
        extraction: drop action verbs, function words, and any phrase
        that appears in ``QUERY_ACTION_WORDS``.  Only NOUN / PROPN
        chunk roots are retained.

    Returns
    -------
    List[str]
        Ordered, deduplicated list of lowercase keyword phrases.
    """
    if not text or not text.strip():
        return []

    nlp = _get_nlp()
    doc = nlp(text[:100_000])

    seen: Set[str] = set()
    phrases: List[str] = []

    for chunk in doc.noun_chunks:
        # Skip chunks whose root is a verb or auxiliary
        if nouns_only and chunk.root.pos_ not in ("NOUN", "PROPN", "NUM"):
            continue
        # Drop determiners, pronouns, and (in nouns_only mode) verbs
        skip_pos = ("DET", "PRON", "VERB", "AUX") if nouns_only else ("DET", "PRON")
        tokens = [t.text for t in chunk if t.pos_ not in skip_pos]
        phrase = " ".join(tokens).strip().lower()
        # In nouns_only mode, drop action words entirely
        if nouns_only and phrase in QUERY_ACTION_WORDS:
            continue
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    return phrases


def compute_phrase_vectors(phrases: List[str]) -> Optional[np.ndarray]:
    """
    Encode *phrases* into a (N, D) embedding matrix.

    Returns ``None`` if *phrases* is empty.
    """
    if not phrases:
        return None
    model = get_sentence_model()
    return model.encode(phrases, convert_to_numpy=True, show_progress_bar=False)


def compute_similarity(
    file_keywords: List[str],
    query_vectors: np.ndarray,
    threshold: float,
) -> Optional[int]:
    """
    Find the best-matching query index for *file_keywords*.

    Parameters
    ----------
    file_keywords:
        Keyword phrases extracted from the file content.
    query_vectors:
        (Q, D) embedding matrix of query keyword phrases.
    threshold:
        Minimum cosine similarity score (0–1).

    Returns
    -------
    int or None
        Index of the best-matching query keyword (with score ≥ *threshold*),
        or ``None`` if no match exceeds the threshold.
    """
    if not file_keywords:
        return None

    model = get_sentence_model()
    file_vecs: np.ndarray = model.encode(
        file_keywords, convert_to_numpy=True, show_progress_bar=False
    )

    # sim_matrix shape: (len(file_keywords), len(query_keywords))
    sim_matrix = cosine_similarity(file_vecs, query_vectors)
    best_score = float(sim_matrix.max())

    if best_score >= threshold:
        # Which query keyword scored highest (column index)?
        best_query_idx = int(sim_matrix.max(axis=0).argmax())
        return best_query_idx

    return None


# ---------------------------------------------------------------------------
# Safe file operation
# ---------------------------------------------------------------------------

def safe_copy_then_delete(src: str | Path, dest_dir: str | Path) -> Path:
    """
    Copy *src* to *dest_dir* and delete the original only after verification.

    Strategy
    --------
    1. Create *dest_dir* (and parents) if needed.
    2. If a file with the same name already exists in *dest_dir*, append a
       numeric suffix (``file_1.ext``, ``file_2.ext``, …) to avoid overwriting.
    3. Copy with ``shutil.copy2`` (preserves timestamps and metadata).
    4. Compare source and destination file sizes.
    5. Only if sizes match, remove the original with ``Path.unlink()``.
    6. If verification fails, the partial copy is removed and an exception
       is raised so the caller knows the source is still intact.

    Parameters
    ----------
    src:
        Source file path.
    dest_dir:
        Destination directory (created if absent).

    Returns
    -------
    Path
        The final destination path of the copied file.

    Raises
    ------
    RuntimeError
        If the copy-verification step fails (size mismatch).
    """
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Resolve name conflicts
    dest = dest_dir / src.name
    if dest.exists():
        stem, suffix = src.stem, src.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    logger.debug("Copying '%s' → '%s'", src.name, dest)
    shutil.copy2(str(src), str(dest))

    # Verify byte size before deleting source
    src_size = src.stat().st_size
    dest_size = dest.stat().st_size
    if src_size != dest_size:
        try:
            dest.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"Copy verification failed for '{src.name}': "
            f"source={src_size}B, destination={dest_size}B. "
            "Source file has NOT been deleted."
        )

    src.unlink()
    logger.debug("Verified and removed original '%s'.", src.name)
    return dest


# ---------------------------------------------------------------------------
# FileOrganizer
# ---------------------------------------------------------------------------

class FileOrganizer:
    """
    Orchestrates the complete file-organisation pipeline.

    Parameters
    ----------
    config:
        An :class:`~ai_file.config.AppConfig` instance.

    Usage
    -----
    >>> organizer = FileOrganizer(config)
    >>> organizer.set_query("annual financial reports 2024")
    >>> organizer.run(progress_cb=my_progress_fn, log_cb=my_log_fn)
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.categorizer = FileCategorizer(config)
        self._db_path = Path(config.db_path)
        self._registry: pd.DataFrame = self._load_registry()

        # NLP state
        self._query_keywords: List[str] = []
        self._query_vectors: Optional[np.ndarray] = None

        # Threading controls
        self._pause_event = threading.Event()
        self._pause_event.set()         # not paused initially
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_query(self, query: str) -> None:
        """
        Set the user query and pre-compute keyword embeddings.

        Only true noun phrases are kept as keyword folder names — action
        verbs and function words (e.g. "organise", "match", "find") are
        filtered out by ``extract_phrases(nouns_only=True)``.
        """
        self._query_keywords = extract_phrases(query, nouns_only=True)
        if not self._query_keywords:
            # Fallback: raw words minus action words and short tokens
            self._query_keywords = [
                w.lower() for w in query.split()
                if len(w) > 2 and w.lower() not in QUERY_ACTION_WORDS
            ]
        logger.info("Query keywords (%d): %s", len(self._query_keywords), self._query_keywords)
        self._query_vectors = compute_phrase_vectors(self._query_keywords)

    def get_all_files(self, folder: str | Path) -> List[Path]:
        """
        Return every file in *folder*.

        Respects ``config.recursive``; non-files (directories, symlinks to
        directories) are silently skipped.
        """
        folder = Path(folder)
        if not folder.is_dir():
            logger.warning("'%s' is not a directory — skipping.", folder)
            return []
        if self.config.recursive:
            return [p for p in folder.rglob("*") if p.is_file()]
        return [p for p in folder.iterdir() if p.is_file()]

    def preview(
        self,
        scan_folder: str | Path,
        output_folder: str | Path,
    ) -> Dict[str, List[str]]:
        """
        Return the projected destination structure without moving files.

        Returns
        -------
        Dict[str, List[str]]
            Mapping of ``category → [destination paths …]``.
        """
        files = [str(f) for f in self.get_all_files(scan_folder)]
        return self.categorizer.preview_structure(files, str(output_folder))

    def run(
        self,
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        log_cb: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Run the full organisation pipeline.

        ALL files are processed:
          - Unsupported extensions  → ``output/Other/``
          - Supported, unselected category → skipped (left in place)
          - Supported, selected category → categorised ± keyword folder

        Empty directories in the source folders are removed after the run.
        """
        self._cancel_event.clear()

        def emit(level: str, msg: str) -> None:
            getattr(logger, level.lower(), logger.info)(msg)
            if log_cb:
                log_cb(level, msg)

        # Collect ALL files from configured source folders
        all_files: List[Path] = []
        for folder in self.config.scan_folders:
            found = self.get_all_files(folder)
            emit("INFO", f"Found {len(found)} files in '{folder}'.")
            all_files.extend(found)

        total = len(all_files)
        emit("INFO", f"{total} total files to process.")

        if total == 0:
            emit("WARNING", "No files found. Nothing to do.")
            return

        output_folder = Path(self.config.output_folder)

        # Submit all tasks to the thread pool
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
            future_to_path = {
                pool.submit(self._process_file, fp, output_folder, emit): fp
                for fp in all_files
            }

            completed = 0
            for future in as_completed(future_to_path):
                fp = future_to_path[future]

                if self._cancel_event.is_set():
                    emit("INFO", "Cancellation requested — stopping.")
                    for pending in future_to_path:
                        pending.cancel()
                    break

                self._pause_event.wait()

                try:
                    future.result()
                except Exception as exc:
                    emit("ERROR", f"Unhandled error for '{fp.name}': {exc}")

                completed += 1
                if progress_cb:
                    progress_cb(completed, total, fp.name)

        self._save_registry()
        emit("INFO", f"Finished. {completed}/{total} files processed. Registry saved.")

        # Clean up empty directories in source folders
        removed = self._cleanup_empty_dirs(self.config.scan_folders)
        if removed:
            emit("INFO", f"Removed {removed} empty folder(s) from source.")

    # ------------------------------------------------------------------
    # Controls (called from GUI thread)
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause processing after the current batch of futures completes."""
        self._pause_event.clear()
        logger.info("Processing paused.")

    def resume(self) -> None:
        """Resume a paused run."""
        self._pause_event.set()
        logger.info("Processing resumed.")

    def cancel(self) -> None:
        """Request cancellation of the current run."""
        self._cancel_event.set()
        self._pause_event.set()     # unblock if currently paused
        logger.info("Cancellation requested.")

    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _process_file(
        self,
        file_path: Path,
        output_folder: Path,
        emit: Callable[[str, str], None],
    ) -> None:
        """
        Classify and move a single file.

        Routing rules
        -------------
        1. Unsupported extension           → ``output/Other/``
        2. Category not in selected list   → skip (left in place)
        3. Semantic keyword match          → ``output/<keyword>/`` (top level)
        4. No match, categorisation on    → ``output/<Category>/``
        5. No match, categorisation off   → ``output/Unsorted/``
        """
        emit("INFO", f"Processing: {file_path.name}")

        # ── 1. Unsupported extension → Other ─────────────────────────────
        if not is_supported(file_path):
            try:
                dest = safe_copy_then_delete(file_path, output_folder / "Other")
                self._update_registry(file_path, dest, "Other")
                emit("INFO", f"  ✓ (unsupported) → Other/{dest.name}")
            except Exception as exc:
                emit("ERROR", f"  ✗ Could not move '{file_path.name}' to Other: {exc}")
            return

        # ── 2. Category determination ─────────────────────────────────────
        if self.config.enable_categorization:
            category = self.categorizer.get_category(file_path)
        else:
            category = "Unsorted"

        # ── 3. Selected-categories check ──────────────────────────────────
        selected = self.config.selected_categories
        if selected and category not in selected:
            emit("INFO", f"  → Skipped (category '{category}' not selected).")
            return

        # ── 4. Preserve structure option ──────────────────────────────────
        category_folder = output_folder / category
        if self.config.preserve_structure:
            for scan_root in self.config.scan_folders:
                try:
                    rel = file_path.relative_to(scan_root)
                    category_folder = category_folder / rel.parent
                    break
                except ValueError:
                    continue

        # ── 5. Semantic keyword matching ──────────────────────────────────
        dest_folder = category_folder   # default: no match
        matched_keyword: Optional[str] = None

        if self._query_vectors is not None:
            try:
                raw_text = extract_text(file_path)
                validate_text(raw_text, min_words=self.config.min_word_count)
                keywords = extract_phrases(raw_text)
                best_idx = compute_similarity(
                    keywords, self._query_vectors, self.config.similarity_threshold
                )
                if best_idx is not None:
                    matched_keyword = self._query_keywords[best_idx]
                    # Query-matched folder lives at OUTPUT root, not inside category
                    dest_folder = output_folder / matched_keyword
                    emit("INFO", f"  → Keyword match: '{matched_keyword}'")
                else:
                    emit("INFO", "  → No keyword match above threshold.")
            except Exception as exc:
                emit("WARNING", f"  Text extraction/matching skipped for '{file_path.name}': {exc}")

        # ── 6. Move the file ──────────────────────────────────────────────
        try:
            dest = safe_copy_then_delete(file_path, dest_folder)
            self._update_registry(file_path, dest, matched_keyword or category)
            emit("INFO", f"  ✓ → {dest.relative_to(output_folder)}")
        except Exception as exc:
            emit("ERROR", f"  ✗ Could not move '{file_path.name}': {exc}")

    # ---- Empty-directory cleanup ─────────────────────────────────────────

    def _cleanup_empty_dirs(self, folders: List[str]) -> int:
        """
        Recursively remove empty directories inside each of *folders*.

        Walks bottom-up so nested empty directories are removed before
        their parents.  The root scan folder itself is never deleted.

        Returns the number of directories removed.
        """
        removed = 0
        for root_str in folders:
            root = Path(root_str)
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root, topdown=False):
                dp = Path(dirpath)
                if dp == root:
                    continue   # never remove the scan root itself
                try:
                    if not any(dp.iterdir()):
                        dp.rmdir()
                        removed += 1
                        logger.debug("Removed empty dir: %s", dp)
                except Exception as exc:
                    logger.debug("Could not remove dir '%s': %s", dp, exc)
        return removed

    # ---- Registry --------------------------------------------------------

    def _update_registry(
        self, src: Path, dest: Path, category: str
    ) -> None:
        """Upsert a file record in the registry DataFrame (thread-safe via GIL)."""
        mask = self._registry["original_path"] == str(src)
        row = {
            "original_path": str(src),
            "current_path":  str(dest),
            "file_name":     dest.name,
            "file_type":     dest.suffix.lower(),
            "category":      category,
        }
        if mask.any():
            for key, val in row.items():
                self._registry.loc[mask, key] = val
        else:
            self._registry = pd.concat(
                [self._registry, pd.DataFrame([row])],
                ignore_index=True,
            )

    def _load_registry(self) -> pd.DataFrame:
        """Load the pickle registry, or return an empty DataFrame."""
        if self._db_path.exists():
            try:
                with open(self._db_path, "rb") as f:
                    data = pickle.load(f)
                if isinstance(data, pd.DataFrame):
                    logger.info("Registry loaded: %d records from '%s'.", len(data), self._db_path)
                    return data
            except Exception as exc:
                logger.warning("Could not load registry from '%s': %s — starting fresh.", self._db_path, exc)

        return pd.DataFrame(
            columns=["original_path", "current_path", "file_name", "file_type", "category"]
        )

    def _save_registry(self) -> None:
        """Persist the registry DataFrame to disk."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._db_path, "wb") as f:
                pickle.dump(self._registry, f)
            logger.debug("Registry saved: %d records → '%s'.", len(self._registry), self._db_path)
        except Exception as exc:
            logger.error("Failed to save registry: %s", exc)
