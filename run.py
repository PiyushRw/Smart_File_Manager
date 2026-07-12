"""
run.py — Entry point for ai_file.

Run from inside the ai_file/ folder:
    python run.py

CLI mode:
    python run.py --cli ^
        --source "C:\\path\\to\\source" ^
        --output "C:\\path\\to\\output" ^
        --query "financial reports 2024" ^
        [--no-recursive] [--no-categorize] [--workers 4]

Custom config:
    python run.py --config path\\to\\config.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ── sys.path fix ─────────────────────────────────────────────────────────────
# When this file is executed from inside ai_file/, Python adds ai_file/ to
# sys.path by default.  We need the PARENT of ai_file/ (i.e. filo/) on the
# path so that  "import ai_file"  resolves correctly as a package.
_HERE = Path(__file__).resolve().parent          # …/filo/ai_file
_PROJECT_ROOT = _HERE.parent                     # …/filo
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
# ─────────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai_file",
        description="Intelligent File Organiser — GUI or CLI mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in headless CLI mode (no GUI).",
    )
    parser.add_argument(
        "--config", metavar="PATH", default=None,
        help="Path to a JSON configuration file.",
    )
    parser.add_argument(
        "--source", metavar="PATH", action="append", dest="sources",
        help="Source folder to scan (repeat for multiple).",
    )
    parser.add_argument(
        "--output", metavar="PATH", default=None,
        help="Destination root folder.",
    )
    parser.add_argument(
        "--query", metavar="TEXT", default="",
        help="Semantic query for keyword-based sub-folder grouping.",
    )
    parser.add_argument(
        "--no-recursive", action="store_true",
        help="Do not scan sub-folders.",
    )
    parser.add_argument(
        "--no-categorize", action="store_true",
        help="Disable automatic file-type categorisation.",
    )
    parser.add_argument(
        "--workers", type=int, default=None, metavar="N",
        help="Number of parallel worker threads.",
    )
    parser.add_argument(
        "--log-file", metavar="PATH", default=None,
        help="Also write log output to this file.",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable verbose DEBUG logging.",
    )
    return parser


def _cli_log(level: str, message: str) -> None:
    print(f"[{level}] {message}", flush=True)


def _cli_progress(current: int, total: int, filename: str) -> None:
    pct = current / total * 100 if total else 0
    bar_len = 30
    filled = int(bar_len * current // max(total, 1))
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\r  [{bar}] {pct:5.1f}%  {filename[:40]:<40}", end="", flush=True)
    if current >= total:
        print()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── Logging ──────────────────────────────────────────────────────────
    from ai_file.utils import setup_logging
    level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_file=args.log_file, level=level)

    # ── Config ───────────────────────────────────────────────────────────
    from ai_file.config import AppConfig
    config_path = Path(args.config) if args.config else None
    config = AppConfig.load(config_path) if config_path else AppConfig.load()

    # Apply CLI overrides
    if args.sources:
        config.scan_folders = args.sources
    if args.output:
        config.output_folder = args.output
    if args.no_recursive:
        config.recursive = False
    if args.no_categorize:
        config.enable_categorization = False
    if args.workers is not None:
        config.max_workers = args.workers

    # ── GUI or CLI ────────────────────────────────────────────────────────
    if args.cli:
        if not config.scan_folders:
            parser.error("CLI mode requires at least one --source folder.")
        if not config.output_folder:
            parser.error("CLI mode requires an --output folder.")

        from ai_file.logic import FileOrganizer
        organizer = FileOrganizer(config)

        query = args.query.strip()
        if query:
            print(f"Setting semantic query: '{query}'")
            organizer.set_query(query)

        print(f"\nScanning {len(config.scan_folders)} folder(s) …\n")
        organizer.run(progress_cb=_cli_progress, log_cb=_cli_log)
        print("\nDone.")
        sys.exit(0)

    else:
        from ai_file.gui import launch
        launch(config)


if __name__ == "__main__":
    main()
