"""
gui.py — Modern, dark/light-themed tkinter GUI for ai_file.

Layout
------
  ┌─────────────────────────────────────────────────────┐
  │  Header bar (title + theme toggle)                  │
  ├────────────┬────────────────────────────────────────┤
  │  Sidebar   │  Content area (Notebook tabs)          │
  │  nav       │  • Organiser                           │
  │            │  • Settings                            │
  │            │  • Log                                 │
  │            │  • About                               │
  └────────────┴────────────────────────────────────────┘

Threading model
---------------
  All long-running work (file scanning, text extraction, model loading) runs
  in a daemon background thread.  The GUI is never blocked.  Progress and log
  updates are delivered via ``root.after()`` calls so they execute safely on
  the Tk event-loop thread.
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

from .config import AppConfig
from .logic import FileOrganizer

# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------

DARK = {
    "bg":           "#0f1117",
    "surface":      "#1a1d27",
    "surface2":     "#22263a",
    "border":       "#2e3248",
    "accent":       "#6c63ff",
    "accent_hover": "#8b85ff",
    "accent2":      "#00d4aa",
    "text":         "#e8eaf6",
    "text_dim":     "#8892b0",
    "text_faint":   "#495670",
    "success":      "#4caf7d",
    "warning":      "#f0c040",
    "error":        "#ff5a5a",
    "info":         "#64b5f6",
    "sidebar_bg":   "#13151f",
    "sidebar_sel":  "#1c1c35",
    "header_bg":    "#0a0c14",
}

LIGHT = {
    "bg":           "#f0f2fa",
    "surface":      "#ffffff",
    "surface2":     "#e8eaf0",
    "border":       "#d0d4e8",
    "accent":       "#5c54e8",
    "accent_hover": "#7b75f5",
    "accent2":      "#00b894",
    "text":         "#1a1d2e",
    "text_dim":     "#555e7a",
    "text_faint":   "#9099b8",
    "success":      "#2e7d52",
    "warning":      "#b8860b",
    "error":        "#c62828",
    "info":         "#1565c0",
    "sidebar_bg":   "#e2e4f0",
    "sidebar_sel":  "#d0d1ee",
    "header_bg":    "#d8daf0",
}

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_FAMILY = "Segoe UI"
FONT_MONO   = "Consolas"

F_TITLE   = (FONT_FAMILY, 22, "bold")
F_HEADING = (FONT_FAMILY, 13, "bold")
F_LABEL   = (FONT_FAMILY, 10)
F_SMALL   = (FONT_FAMILY,  9)
F_BUTTON  = (FONT_FAMILY, 10, "bold")
F_MONO    = (FONT_MONO,    9)


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

class StyledButton(tk.Canvas):
    """
    A canvas-drawn rounded-rectangle button with hover and click animations.
    """

    def __init__(
        self,
        parent,
        text: str,
        command: Optional[Callable] = None,
        color: Optional[str] = None,
        text_color: Optional[str] = None,
        width: int = 140,
        height: int = 36,
        radius: int = 8,
        **kwargs,
    ):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, **kwargs)
        self.command = command
        self.text = text
        self.radius = radius
        self.width = width
        self.height = height
        self._pressed = False

        # Color will be set when theme is applied; store defaults
        self._color = color
        self._text_color = text_color

        self._draw(color or "#6c63ff", text_color or "#ffffff")

        self.bind("<Enter>",        self._on_enter)
        self.bind("<Leave>",        self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self, bg: str, fg: str, scale: float = 1.0) -> None:
        self.delete("all")
        w, h, r = int(self.width * scale), int(self.height * scale), self.radius
        x0, y0 = (self.width - w) // 2, (self.height - h) // 2
        x1, y1 = x0 + w, y0 + h

        self.create_arc(x0, y0, x0+2*r, y0+2*r, start=90, extent=90, fill=bg, outline=bg)
        self.create_arc(x1-2*r, y0, x1, y0+2*r, start=0, extent=90, fill=bg, outline=bg)
        self.create_arc(x0, y1-2*r, x0+2*r, y1, start=180, extent=90, fill=bg, outline=bg)
        self.create_arc(x1-2*r, y1-2*r, x1, y1, start=270, extent=90, fill=bg, outline=bg)
        self.create_rectangle(x0+r, y0, x1-r, y1, fill=bg, outline=bg)
        self.create_rectangle(x0, y0+r, x1, y1-r, fill=bg, outline=bg)
        self.create_text(
            self.width // 2, self.height // 2,
            text=self.text, fill=fg, font=F_BUTTON,
        )

    def _on_enter(self, _=None) -> None:
        c = self._color or "#6c63ff"
        self._draw(_lighten(c, 0.15), self._text_color or "#ffffff")
        self.config(cursor="hand2")

    def _on_leave(self, _=None) -> None:
        self._draw(self._color or "#6c63ff", self._text_color or "#ffffff")
        self.config(cursor="")

    def _on_press(self, _=None) -> None:
        c = self._color or "#6c63ff"
        self._draw(_darken(c, 0.1), self._text_color or "#ffffff", scale=0.96)

    def _on_release(self, _=None) -> None:
        self._draw(self._color or "#6c63ff", self._text_color or "#ffffff")
        if self.command:
            self.command()

    def update_color(self, color: str, text_color: str = "#ffffff") -> None:
        self._color = color
        self._text_color = text_color
        self._draw(color, text_color)


class SectionFrame(tk.Frame):
    """A labeled section card with a subtle border."""

    def __init__(self, parent, title: str, colors: Dict[str, str], **kwargs):
        super().__init__(parent, bg=colors["surface"], **kwargs)
        self._colors = colors

        header = tk.Frame(self, bg=colors["surface"])
        header.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(
            header, text=title, font=F_HEADING,
            fg=colors["accent"], bg=colors["surface"],
        ).pack(side="left")

        sep = tk.Frame(self, bg=colors["border"], height=1)
        sep.pack(fill="x", padx=12, pady=(0, 8))

        self.body = tk.Frame(self, bg=colors["surface"])
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 10))


class ScrollableFrame(tk.Frame):
    """A vertically scrollable container."""

    def __init__(self, parent, colors: Dict[str, str], **kwargs):
        super().__init__(parent, bg=colors["bg"], **kwargs)
        canvas = tk.Canvas(self, bg=colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=colors["bg"])

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))


# ---------------------------------------------------------------------------
# Colour utilities
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))   # type: ignore


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(hex_color: str, amount: float = 0.1) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        min(255, int(r + (255 - r) * amount)),
        min(255, int(g + (255 - g) * amount)),
        min(255, int(b + (255 - b) * amount)),
    )


def _darken(hex_color: str, amount: float = 0.1) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    return _rgb_to_hex(
        max(0, int(r * (1 - amount))),
        max(0, int(g * (1 - amount))),
        max(0, int(b * (1 - amount))),
    )


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class App(tk.Tk):
    """
    Main application window for ai_file.

    Manages theme switching, sidebar navigation, and inter-tab communication.
    """

    NAV_ITEMS = [
        ("📂  Organiser",  "organiser"),
        ("⚙️   Settings",  "settings"),
        ("📋  Log",        "log"),
        ("ℹ️   About",     "about"),
    ]

    def __init__(self, config: AppConfig):
        super().__init__()
        self.config_data = config
        self._colors: Dict[str, str] = DARK if config.theme == "dark" else LIGHT
        self._active_tab = "organiser"
        self._organizer: Optional[FileOrganizer] = None
        self._run_thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue = queue.Queue()
        self._start_time: Optional[float] = None

        self._setup_window()
        self._build_ui()
        self._poll_log_queue()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.title("ai_file — Intelligent File Organiser")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(bg=self._colors["bg"])
        try:
            self.iconbitmap("")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        c = self._colors

        # ── Header ──────────────────────────────────────────────────────
        self._header = tk.Frame(self, bg=c["header_bg"], height=56)
        self._header.pack(fill="x", side="top")
        self._header.pack_propagate(False)

        tk.Label(
            self._header,
            text="✦ ai_file",
            font=(FONT_FAMILY, 16, "bold"),
            fg=c["accent"],
            bg=c["header_bg"],
        ).pack(side="left", padx=20, pady=12)

        tk.Label(
            self._header,
            text="Intelligent File Organiser",
            font=(FONT_FAMILY, 10),
            fg=c["text_dim"],
            bg=c["header_bg"],
        ).pack(side="left", pady=12)

        self._theme_btn = tk.Label(
            self._header,
            text="☀  Light" if self._colors is DARK else "🌙  Dark",
            font=(FONT_FAMILY, 9, "bold"),
            fg=c["text_dim"],
            bg=c["header_bg"],
            cursor="hand2",
            padx=12, pady=6,
        )
        self._theme_btn.pack(side="right", padx=16)
        self._theme_btn.bind("<Button-1>", lambda _: self._toggle_theme())

        # ── Body (sidebar + content) ─────────────────────────────────────
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar = tk.Frame(body, bg=c["sidebar_bg"], width=180)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        self._nav_labels: Dict[str, tk.Label] = {}
        for display, key in self.NAV_ITEMS:
            lbl = tk.Label(
                self._sidebar,
                text=display,
                font=(FONT_FAMILY, 10),
                fg=c["text_dim"],
                bg=c["sidebar_bg"],
                anchor="w",
                padx=16,
                pady=10,
                cursor="hand2",
            )
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda _, k=key: self._switch_tab(k))
            lbl.bind("<Enter>",    lambda e, lbl=lbl, k=key: self._nav_hover(lbl, k, True))
            lbl.bind("<Leave>",    lambda e, lbl=lbl, k=key: self._nav_hover(lbl, k, False))
            self._nav_labels[key] = lbl

        # Version at bottom of sidebar
        tk.Label(
            self._sidebar,
            text="v2.0.0",
            font=F_SMALL,
            fg=c["text_faint"],
            bg=c["sidebar_bg"],
        ).pack(side="bottom", pady=10)

        # Content area
        self._content = tk.Frame(body, bg=c["bg"])
        self._content.pack(side="left", fill="both", expand=True)

        # Build all tabs
        self._tabs: Dict[str, tk.Frame] = {}
        self._build_organiser_tab()
        self._build_settings_tab()
        self._build_log_tab()
        self._build_about_tab()

        self._switch_tab("organiser")

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _switch_tab(self, key: str) -> None:
        c = self._colors
        # Hide all tabs
        for tab in self._tabs.values():
            tab.pack_forget()
        # Show selected
        self._tabs[key].pack(fill="both", expand=True)
        self._active_tab = key

        # Update sidebar highlight
        for nav_key, lbl in self._nav_labels.items():
            if nav_key == key:
                lbl.config(fg=c["accent"], bg=c["sidebar_sel"], font=(FONT_FAMILY, 10, "bold"))
            else:
                lbl.config(fg=c["text_dim"], bg=c["sidebar_bg"], font=(FONT_FAMILY, 10))

    def _nav_hover(self, lbl: tk.Label, key: str, entering: bool) -> None:
        if key == self._active_tab:
            return
        c = self._colors
        lbl.config(bg=c["sidebar_sel"] if entering else c["sidebar_bg"])

    # ------------------------------------------------------------------
    # ORGANISER TAB
    # ------------------------------------------------------------------

    def _build_organiser_tab(self) -> None:
        c = self._colors
        tab = tk.Frame(self._content, bg=c["bg"])
        self._tabs["organiser"] = tab

        # Scrollable body
        scroller = ScrollableFrame(tab, colors=c)
        scroller.pack(fill="both", expand=True, padx=0, pady=0)
        body = scroller.inner
        body.columnconfigure(0, weight=1)

        # ── Source folders section ───────────────────────────────────────
        src_sec = SectionFrame(body, "📂  Source Folders", c)
        src_sec.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        body.rowconfigure(0, weight=0)

        self._folder_listbox = tk.Listbox(
            src_sec.body,
            bg=c["surface2"], fg=c["text"], selectbackground=c["accent"],
            selectforeground="#ffffff", font=F_MONO,
            height=4, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        self._folder_listbox.pack(fill="x", pady=(0, 8))

        # Pre-populate from saved config
        for saved_folder in self.config_data.scan_folders:
            self._folder_listbox.insert("end", saved_folder)

        btn_row = tk.Frame(src_sec.body, bg=c["surface"])
        btn_row.pack(fill="x")

        self._btn_add_folder = StyledButton(
            btn_row, "＋ Add Folder",
            command=self._add_folder,
            color=c["accent"], width=130, height=32,
            bg=c["surface"],
        )
        self._btn_add_folder.pack(side="left", padx=(0, 8))

        self._btn_remove_folder = StyledButton(
            btn_row, "✕ Remove",
            command=self._remove_folder,
            color=c["surface2"], text_color=c["text"], width=100, height=32,
            bg=c["surface"],
        )
        self._btn_remove_folder.pack(side="left")

        # Recursive toggle
        self._recursive_var = tk.BooleanVar(value=self.config_data.recursive)
        tk.Checkbutton(
            src_sec.body,
            text="Scan sub-folders recursively",
            variable=self._recursive_var,
            font=F_LABEL,
            fg=c["text_dim"], bg=c["surface"],
            activebackground=c["surface"], activeforeground=c["text"],
            selectcolor=c["surface2"],
        ).pack(anchor="w", pady=(8, 0))

        # ── Output folder section ────────────────────────────────────────
        out_sec = SectionFrame(body, "📁  Destination Folder", c)
        out_sec.grid(row=1, column=0, sticky="ew", padx=16, pady=8)

        out_row = tk.Frame(out_sec.body, bg=c["surface"])
        out_row.pack(fill="x")

        self._output_var = tk.StringVar(value=self.config_data.output_folder)
        self._output_entry = tk.Entry(
            out_row,
            textvariable=self._output_var,
            font=F_MONO, bg=c["surface2"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=4,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        self._output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._btn_browse_out = StyledButton(
            out_row, "Browse",
            command=self._browse_output,
            color=c["accent"], width=90, height=32,
            bg=c["surface"],
        )
        self._btn_browse_out.pack(side="right")

        # ── Query section ─────────────────────────────────────────────────
        query_sec = SectionFrame(body, "🔍  Semantic Query (optional)", c)
        query_sec.grid(row=2, column=0, sticky="ew", padx=16, pady=8)

        tk.Label(
            query_sec.body,
            text="Files matching your query will be grouped into named sub-folders.",
            font=F_SMALL, fg=c["text_dim"], bg=c["surface"],
        ).pack(anchor="w", pady=(0, 6))

        self._query_var = tk.StringVar()
        tk.Entry(
            query_sec.body,
            textvariable=self._query_var,
            font=F_LABEL, bg=c["surface2"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=4,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        ).pack(fill="x")

        # ── Categorisation toggle ─────────────────────────────────────────
        cat_sec = SectionFrame(body, "🗂  Categorisation", c)
        cat_sec.grid(row=3, column=0, sticky="ew", padx=16, pady=8)

        self._cat_var = tk.BooleanVar(value=self.config_data.enable_categorization)
        tk.Checkbutton(
            cat_sec.body,
            text="Enable automatic file categorisation",
            variable=self._cat_var,
            font=F_LABEL,
            fg=c["text"], bg=c["surface"],
            activebackground=c["surface"], activeforeground=c["text"],
            selectcolor=c["surface2"],
        ).pack(anchor="w")

        # ── File-type selection checkboxes ────────────────────────────────
        filetype_sec = SectionFrame(body, "☑  File Types to Process", c)
        filetype_sec.grid(row=4, column=0, sticky="ew", padx=16, pady=8)

        tk.Label(
            filetype_sec.body,
            text="Unchecked categories are skipped. Leave all unchecked to process every type.",
            font=F_SMALL, fg=c["text_dim"], bg=c["surface"],
        ).pack(anchor="w", pady=(0, 6))

        # Select All / Clear All
        sel_row = tk.Frame(filetype_sec.body, bg=c["surface"])
        sel_row.pack(anchor="w", pady=(0, 6))
        tk.Label(sel_row, text="Quick:", font=F_SMALL, fg=c["text_dim"],
                 bg=c["surface"]).pack(side="left", padx=(0, 6))
        StyledButton(sel_row, "Select All", command=self._select_all_categories,
                     color=c["accent"], width=90, height=24, bg=c["surface"]).pack(side="left", padx=(0, 6))
        StyledButton(sel_row, "Clear All", command=self._clear_all_categories,
                     color=c["surface2"], text_color=c["text"], width=80, height=24,
                     bg=c["surface"]).pack(side="left")

        # 2-column grid of checkboxes
        self._cat_check_vars: Dict[str, tk.BooleanVar] = {}
        grid_frame = tk.Frame(filetype_sec.body, bg=c["surface"])
        grid_frame.pack(fill="x")
        categories = list(self.config_data.categories.keys()) + ["Other", "Misc"]
        selected_set = set(self.config_data.selected_categories)
        for i, cat_name in enumerate(categories):
            var = tk.BooleanVar(value=(cat_name in selected_set) if selected_set else False)
            self._cat_check_vars[cat_name] = var
            tk.Checkbutton(
                grid_frame, text=cat_name, variable=var,
                font=F_SMALL, fg=c["text"], bg=c["surface"],
                activebackground=c["surface"], activeforeground=c["text"],
                selectcolor=c["surface2"], anchor="w",
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 20), pady=1)

        # ── Preview tree ──────────────────────────────────────────────────
        prev_sec = SectionFrame(body, "👁  Destination Preview", c)
        prev_sec.grid(row=5, column=0, sticky="ew", padx=16, pady=8)

        self._preview_tree = ttk.Treeview(
            prev_sec.body,
            columns=("dest",),
            show="tree headings",
            height=6,
        )
        self._preview_tree.heading("#0", text="Category")
        self._preview_tree.heading("dest", text="Files")
        self._preview_tree.column("#0", width=150)
        self._preview_tree.column("dest", width=500)
        self._preview_tree.pack(fill="x")
        self._apply_treeview_style()

        preview_btn = StyledButton(
            prev_sec.body, "Generate Preview",
            command=self._generate_preview,
            color=c["accent2"], width=160, height=32,
            bg=c["surface"],
        )
        preview_btn.pack(anchor="w", pady=(8, 0))

        # ── Progress section ──────────────────────────────────────────────
        prog_sec = SectionFrame(body, "⏱  Progress", c)
        prog_sec.grid(row=6, column=0, sticky="ew", padx=16, pady=8)

        tk.Label(prog_sec.body, text="Overall progress:", font=F_SMALL,
                 fg=c["text_dim"], bg=c["surface"]).pack(anchor="w")

        self._overall_var = tk.DoubleVar(value=0)
        self._overall_bar = ttk.Progressbar(
            prog_sec.body, variable=self._overall_var,
            maximum=100, mode="determinate",
        )
        self._overall_bar.pack(fill="x", pady=(2, 8))

        self._file_label = tk.Label(prog_sec.body, text="Ready.", font=F_SMALL,
                                    fg=c["text_dim"], bg=c["surface"], anchor="w")
        self._file_label.pack(fill="x")

        self._eta_label = tk.Label(prog_sec.body, text="", font=F_SMALL,
                                   fg=c["accent"], bg=c["surface"], anchor="w")
        self._eta_label.pack(fill="x")

        # ── Control buttons ───────────────────────────────────────────────
        ctrl_sec = SectionFrame(body, "▶  Controls", c)
        ctrl_sec.grid(row=7, column=0, sticky="ew", padx=16, pady=(8, 20))

        btn_row2 = tk.Frame(ctrl_sec.body, bg=c["surface"])
        btn_row2.pack(fill="x")

        self._btn_run = StyledButton(
            btn_row2, "▶ Run",
            command=self._run_organizer,
            color=c["success"], width=120, height=38,
            bg=c["surface"],
        )
        self._btn_run.pack(side="left", padx=(0, 8))

        self._btn_pause = StyledButton(
            btn_row2, "⏸ Pause",
            command=self._pause_organizer,
            color=c["warning"], text_color="#1a1a1a", width=110, height=38,
            bg=c["surface"],
        )
        self._btn_pause.pack(side="left", padx=(0, 8))

        self._btn_cancel = StyledButton(
            btn_row2, "✕ Cancel",
            command=self._cancel_organizer,
            color=c["error"], width=110, height=38,
            bg=c["surface"],
        )
        self._btn_cancel.pack(side="left")

        self._status_label = tk.Label(
            ctrl_sec.body, text="",
            font=(FONT_FAMILY, 9, "bold"),
            fg=c["success"], bg=c["surface"], anchor="w",
        )
        self._status_label.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------
    # SETTINGS TAB
    # ------------------------------------------------------------------

    def _build_settings_tab(self) -> None:
        c = self._colors
        tab = tk.Frame(self._content, bg=c["bg"])
        self._tabs["settings"] = tab

        scroller = ScrollableFrame(tab, colors=c)
        scroller.pack(fill="both", expand=True)
        body = scroller.inner
        body.columnconfigure(0, weight=1)

        # ── NLP settings ─────────────────────────────────────────────────
        nlp_sec = SectionFrame(body, "🧠  NLP & Similarity", c)
        nlp_sec.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

        self._st_model_var = tk.StringVar(value=self.config_data.sentence_model)
        self._make_labeled_entry(nlp_sec.body, c, "SentenceTransformer model:",
                                 self._st_model_var)

        self._threshold_var = tk.DoubleVar(value=self.config_data.similarity_threshold)
        tk.Label(nlp_sec.body, text="Similarity threshold (0–1):",
                 font=F_LABEL, fg=c["text_dim"], bg=c["surface"]).pack(anchor="w", pady=(8, 2))
        thresh_row = tk.Frame(nlp_sec.body, bg=c["surface"])
        thresh_row.pack(fill="x")
        tk.Scale(
            thresh_row, from_=0.1, to=0.9, resolution=0.05,
            variable=self._threshold_var, orient="horizontal",
            bg=c["surface"], fg=c["text"], troughcolor=c["surface2"],
            activebackground=c["accent"], highlightthickness=0, bd=0,
        ).pack(side="left", fill="x", expand=True)
        tk.Label(thresh_row, textvariable=self._threshold_var, width=4,
                 font=F_LABEL, fg=c["accent"], bg=c["surface"]).pack(side="right")

        self._min_words_var = tk.IntVar(value=self.config_data.min_word_count)
        self._make_labeled_spinbox(nlp_sec.body, c, "Minimum word count (warning):",
                                   self._min_words_var, 1, 500)

        # ── Whisper settings ──────────────────────────────────────────────
        whisper_sec = SectionFrame(body, "🎙  Whisper (Audio/Video)", c)
        whisper_sec.grid(row=1, column=0, sticky="ew", padx=16, pady=8)

        self._whisper_var = tk.StringVar(value=self.config_data.whisper_model_size)
        for size in ("tiny", "base", "small", "medium", "large"):
            tk.Radiobutton(
                whisper_sec.body, text=size.capitalize(), value=size,
                variable=self._whisper_var,
                font=F_LABEL, fg=c["text"], bg=c["surface"],
                activebackground=c["surface"], selectcolor=c["surface2"],
            ).pack(side="left", padx=8)

        # ── GPU settings ──────────────────────────────────────────────────
        gpu_sec = SectionFrame(body, "⚡  GPU Acceleration", c)
        gpu_sec.grid(row=2, column=0, sticky="ew", padx=16, pady=8)

        self._gpu_var = tk.BooleanVar(value=self.config_data.use_gpu)
        tk.Checkbutton(
            gpu_sec.body,
            text="Enable GPU acceleration (CUDA) — falls back to CPU if unavailable",
            variable=self._gpu_var,
            font=F_LABEL, fg=c["text"], bg=c["surface"],
            activebackground=c["surface"], activeforeground=c["text"],
            selectcolor=c["surface2"],
        ).pack(anchor="w")

        # ── Performance settings ──────────────────────────────────────────
        perf_sec = SectionFrame(body, "⚙️  Performance", c)
        perf_sec.grid(row=3, column=0, sticky="ew", padx=16, pady=8)

        self._workers_var = tk.IntVar(value=self.config_data.max_workers)
        self._make_labeled_spinbox(perf_sec.body, c, "Parallel worker threads:", self._workers_var, 1, 16)

        # ── Categories editor ─────────────────────────────────────────────
        cat_sec = SectionFrame(body, "🗂  File Categories", c)
        cat_sec.grid(row=4, column=0, sticky="ew", padx=16, pady=8)

        tk.Label(
            cat_sec.body,
            text="Select a category to view / edit its extensions:",
            font=F_SMALL, fg=c["text_dim"], bg=c["surface"],
        ).pack(anchor="w", pady=(0, 6))

        cat_list_row = tk.Frame(cat_sec.body, bg=c["surface"])
        cat_list_row.pack(fill="x")

        self._cat_listbox = tk.Listbox(
            cat_list_row,
            bg=c["surface2"], fg=c["text"], selectbackground=c["accent"],
            font=F_LABEL, height=8, relief="flat", bd=0,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        self._cat_listbox.pack(side="left", fill="y", padx=(0, 8))
        for cat_name in self.config_data.categories:
            self._cat_listbox.insert("end", cat_name)
        self._cat_listbox.bind("<<ListboxSelect>>", self._on_category_select)

        cat_right = tk.Frame(cat_list_row, bg=c["surface"])
        cat_right.pack(side="left", fill="both", expand=True)

        tk.Label(cat_right, text="Extensions (comma-separated):",
                 font=F_SMALL, fg=c["text_dim"], bg=c["surface"]).pack(anchor="w")

        self._ext_var = tk.StringVar()
        self._ext_entry = tk.Entry(
            cat_right, textvariable=self._ext_var,
            font=F_MONO, bg=c["surface2"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=4,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        self._ext_entry.pack(fill="x", pady=(2, 8))

        cat_btn_row = tk.Frame(cat_right, bg=c["surface"])
        cat_btn_row.pack(anchor="w")
        StyledButton(cat_btn_row, "Update", command=self._update_category,
                     color=c["accent"], width=90, height=28, bg=c["surface"]).pack(side="left", padx=(0, 6))
        StyledButton(cat_btn_row, "Add New", command=self._add_category,
                     color=c["accent2"], width=90, height=28, bg=c["surface"]).pack(side="left", padx=(0, 6))
        StyledButton(cat_btn_row, "Delete", command=self._delete_category,
                     color=c["error"], width=80, height=28, bg=c["surface"]).pack(side="left")

        # ── Excluded extensions ───────────────────────────────────────────
        excl_sec = SectionFrame(body, "🚫  Excluded Extensions", c)
        excl_sec.grid(row=5, column=0, sticky="ew", padx=16, pady=8)

        tk.Label(excl_sec.body, text="Extensions to skip (comma-separated):",
                 font=F_SMALL, fg=c["text_dim"], bg=c["surface"]).pack(anchor="w", pady=(0, 4))

        self._excl_var = tk.StringVar(
            value=", ".join(self.config_data.excluded_extensions)
        )
        tk.Entry(
            excl_sec.body, textvariable=self._excl_var,
            font=F_MONO, bg=c["surface2"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=4,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        ).pack(fill="x")

        # ── Config actions ────────────────────────────────────────────────
        cfg_sec = SectionFrame(body, "💾  Configuration", c)
        cfg_sec.grid(row=6, column=0, sticky="ew", padx=16, pady=(8, 20))

        cfg_btn_row = tk.Frame(cfg_sec.body, bg=c["surface"])
        cfg_btn_row.pack(fill="x")

        StyledButton(cfg_btn_row, "💾 Save", command=self._save_settings,
                     color=c["success"], width=110, height=36, bg=c["surface"]).pack(side="left", padx=(0, 8))
        StyledButton(cfg_btn_row, "📤 Export", command=self._export_config,
                     color=c["accent"], width=110, height=36, bg=c["surface"]).pack(side="left", padx=(0, 8))
        StyledButton(cfg_btn_row, "📥 Import", command=self._import_config,
                     color=c["accent"], width=110, height=36, bg=c["surface"]).pack(side="left", padx=(0, 8))
        StyledButton(cfg_btn_row, "↺ Reset", command=self._reset_settings,
                     color=c["error"], width=100, height=36, bg=c["surface"]).pack(side="left")

    # ------------------------------------------------------------------
    # LOG TAB
    # ------------------------------------------------------------------

    def _build_log_tab(self) -> None:
        c = self._colors
        tab = tk.Frame(self._content, bg=c["bg"])
        self._tabs["log"] = tab

        # Toolbar
        toolbar = tk.Frame(tab, bg=c["surface"], pady=6)
        toolbar.pack(fill="x", padx=0, side="top")

        tk.Label(toolbar, text="  📋 Live Log", font=F_HEADING,
                 fg=c["accent"], bg=c["surface"]).pack(side="left")

        StyledButton(toolbar, "Clear", command=self._clear_log,
                     color=c["surface2"], text_color=c["text"],
                     width=80, height=28, bg=c["surface"]).pack(side="right", padx=12)

        sep = tk.Frame(tab, bg=c["border"], height=1)
        sep.pack(fill="x")

        # Log text area
        log_frame = tk.Frame(tab, bg=c["bg"])
        log_frame.pack(fill="both", expand=True, padx=12, pady=12)

        self._log_text = tk.Text(
            log_frame,
            bg=c["surface"], fg=c["text"],
            font=F_MONO, wrap="none", state="disabled",
            relief="flat", bd=0,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        self._log_text.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        sb.pack(side="right", fill="y")
        self._log_text.configure(yscrollcommand=sb.set)

        # Configure colour tags
        self._log_text.tag_configure("INFO",    foreground=c["text"])
        self._log_text.tag_configure("WARNING", foreground=c["warning"])
        self._log_text.tag_configure("ERROR",   foreground=c["error"])
        self._log_text.tag_configure("SUCCESS", foreground=c["success"])
        self._log_text.tag_configure("DIM",     foreground=c["text_faint"])

    # ------------------------------------------------------------------
    # ABOUT TAB
    # ------------------------------------------------------------------

    def _build_about_tab(self) -> None:
        c = self._colors
        tab = tk.Frame(self._content, bg=c["bg"])
        self._tabs["about"] = tab

        center = tk.Frame(tab, bg=c["bg"])
        center.place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(center, text="✦ ai_file", font=(FONT_FAMILY, 36, "bold"),
                 fg=c["accent"], bg=c["bg"]).pack(pady=(0, 4))

        tk.Label(center, text="Intelligent File Organiser  v2.0.0",
                 font=(FONT_FAMILY, 13), fg=c["text_dim"], bg=c["bg"]).pack()

        tk.Frame(center, bg=c["border"], height=1, width=300).pack(pady=20)

        desc = (
            "ai_file extracts text from dozens of file formats,\n"
            "classifies them by type, and semantically groups them\n"
            "using SentenceTransformer embeddings and spaCy NLP.\n\n"
            "GPU acceleration (CUDA) is used automatically\n"
            "for OCR (EasyOCR) and transcription (Whisper)\n"
            "when compatible hardware is detected."
        )
        tk.Label(center, text=desc, font=(FONT_FAMILY, 10),
                 fg=c["text_dim"], bg=c["bg"], justify="center").pack()

        tk.Frame(center, bg=c["border"], height=1, width=300).pack(pady=20)

        tech_label = (
            "Technologies: Python · tkinter · spaCy · SentenceTransformers\n"
            "pdfplumber · EasyOCR · faster-whisper · moviepy · pandas"
        )
        tk.Label(center, text=tech_label, font=(FONT_FAMILY, 9),
                 fg=c["text_faint"], bg=c["bg"], justify="center").pack()

    # ------------------------------------------------------------------
    # Category checkbox helpers
    # ------------------------------------------------------------------

    def _select_all_categories(self) -> None:
        """Tick every file-type checkbox."""
        for var in self._cat_check_vars.values():
            var.set(True)

    def _clear_all_categories(self) -> None:
        """Untick every file-type checkbox (= process all types)."""
        for var in self._cat_check_vars.values():
            var.set(False)

    # ------------------------------------------------------------------
    # Organiser actions
    # ------------------------------------------------------------------

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Select Source Folder",
            initialdir=str(Path.home()),
        )
        if not folder:
            return
        if folder in self.config_data.scan_folders:
            messagebox.showinfo(
                "Already added",
                f"This folder is already in the source list:\n{folder}",
            )
            return
        if folder and folder not in self.config_data.scan_folders:
            self.config_data.scan_folders.append(folder)
            self._folder_listbox.insert("end", folder)

    def _remove_folder(self) -> None:
        sel = self._folder_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        folder = self._folder_listbox.get(idx)
        self._folder_listbox.delete(idx)
        if folder in self.config_data.scan_folders:
            self.config_data.scan_folders.remove(folder)

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(
            title="Select Destination Folder",
            initialdir=str(Path.home()),
        )
        if folder:
            self._output_var.set(folder)

    def _generate_preview(self) -> None:
        folders = list(self._folder_listbox.get(0, "end"))
        output  = self._output_var.get().strip()

        if not folders:
            messagebox.showwarning("No source folders", "Add at least one source folder.")
            return
        if not output:
            messagebox.showwarning("No destination", "Set a destination folder.")
            return

        self._apply_settings_to_config()
        organizer = FileOrganizer(self.config_data)

        # Clear tree
        for item in self._preview_tree.get_children():
            self._preview_tree.delete(item)

        for folder in folders:
            preview = organizer.preview(folder, output)
            for category, paths in sorted(preview.items()):
                node = self._preview_tree.insert("", "end", text=f"  {category}",
                                                 values=(f"{len(paths)} files",))
                for p in paths[:20]:
                    self._preview_tree.insert(node, "end", text="",
                                              values=(Path(p).name,))
                if len(paths) > 20:
                    self._preview_tree.insert(node, "end", text="",
                                              values=(f"… and {len(paths)-20} more",))

    def _run_organizer(self) -> None:
        if self._run_thread and self._run_thread.is_alive():
            messagebox.showinfo("Already running", "A run is already in progress.")
            return

        output = self._output_var.get().strip()
        folders = list(self._folder_listbox.get(0, "end"))

        if not folders:
            messagebox.showwarning("No source folders", "Add at least one source folder.")
            return
        if not output:
            messagebox.showwarning("No destination", "Set a destination folder.")
            return

        self._apply_settings_to_config()
        self.config_data.output_folder = output

        self._organizer = FileOrganizer(self.config_data)

        query = self._query_var.get().strip()
        if query:
            self._organizer.set_query(query)

        self._overall_var.set(0)
        self._start_time = time.time()
        self._status_label.config(text="Running…", fg=self._colors["warning"])

        self._run_thread = threading.Thread(
            target=self._organizer.run,
            kwargs={
                "progress_cb": self._on_progress,
                "log_cb":      self._on_log,
            },
            daemon=True,
        )
        self._run_thread.start()
        self._switch_tab("log")

    def _pause_organizer(self) -> None:
        if not self._organizer:
            return
        if self._organizer.is_paused:
            self._organizer.resume()
            self._btn_pause.text = "⏸ Pause"
            self._btn_pause._draw(self._colors["warning"], "#1a1a1a")
            self._status_label.config(text="Running…", fg=self._colors["warning"])
        else:
            self._organizer.pause()
            self._btn_pause.text = "▶ Resume"
            self._btn_pause._draw(self._colors["success"], "#ffffff")
            self._status_label.config(text="Paused.", fg=self._colors["info"])

    def _cancel_organizer(self) -> None:
        if self._organizer:
            self._organizer.cancel()
            self._status_label.config(text="Cancelling…", fg=self._colors["error"])

    # Progress callback (called from worker thread → routed via queue)
    def _on_progress(self, current: int, total: int, filename: str) -> None:
        pct = (current / total * 100) if total else 0
        elapsed = time.time() - (self._start_time or time.time())
        eta = ""
        if current > 0 and current < total:
            remaining = elapsed / current * (total - current)
            mins, secs = divmod(int(remaining), 60)
            eta = f"ETA: {mins}m {secs}s"
        self._log_queue.put(("PROGRESS", (pct, filename, eta, current, total)))

    # Log callback (called from worker thread → routed via queue)
    def _on_log(self, level: str, message: str) -> None:
        self._log_queue.put(("LOG", (level, message)))

    # Poll the queue on the Tk event loop (safe UI updates)
    def _poll_log_queue(self) -> None:
        while not self._log_queue.empty():
            msg_type, payload = self._log_queue.get_nowait()
            if msg_type == "LOG":
                level, message = payload
                self._append_log(level, message)
            elif msg_type == "PROGRESS":
                pct, filename, eta, current, total = payload
                self._overall_var.set(pct)
                self._file_label.config(
                    text=f"[{current}/{total}]  {filename}"
                )
                self._eta_label.config(text=eta)
                if current >= total:
                    self._status_label.config(
                        text="✓ Completed!", fg=self._colors["success"]
                    )
        self.after(100, self._poll_log_queue)

    def _append_log(self, level: str, message: str) -> None:
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")

        # Limit log lines
        lines = int(self._log_text.index("end-1c").split(".")[0])
        if lines > self.config_data.max_log_lines:
            self._log_text.delete("1.0", "200.0")

        self._log_text.insert("end", f"[{ts}] ", "DIM")
        tag = level if level in ("INFO", "WARNING", "ERROR", "SUCCESS") else "INFO"
        self._log_text.insert("end", f"{message}\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Settings actions
    # ------------------------------------------------------------------

    def _on_category_select(self, _=None) -> None:
        sel = self._cat_listbox.curselection()
        if not sel:
            return
        cat_name = self._cat_listbox.get(sel[0])
        exts = self.config_data.categories.get(cat_name, [])
        self._ext_var.set(", ".join(exts))

    def _update_category(self) -> None:
        sel = self._cat_listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Select a category first.")
            return
        cat_name = self._cat_listbox.get(sel[0])
        raw = self._ext_var.get()
        exts = [e.strip().lower() for e in raw.split(",") if e.strip()]
        self.config_data.categories[cat_name] = exts
        messagebox.showinfo("Updated", f"'{cat_name}' updated with {len(exts)} extensions.")

    def _add_category(self) -> None:
        from tkinter.simpledialog import askstring
        name = askstring("New Category", "Enter category name:")
        if not name:
            return
        raw = self._ext_var.get()
        exts = [e.strip().lower() for e in raw.split(",") if e.strip()]
        self.config_data.categories[name] = exts
        self._cat_listbox.insert("end", name)

    def _delete_category(self) -> None:
        sel = self._cat_listbox.curselection()
        if not sel:
            return
        cat_name = self._cat_listbox.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete category '{cat_name}'?"):
            del self.config_data.categories[cat_name]
            self._cat_listbox.delete(sel[0])

    def _save_settings(self) -> None:
        self._apply_settings_to_config()
        self.config_data.save()
        messagebox.showinfo("Saved", "Settings saved successfully.")

    def _export_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export Configuration",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            self._apply_settings_to_config()
            self.config_data.export_profile(path)
            messagebox.showinfo("Exported", f"Configuration exported to:\n{path}")

    def _import_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Configuration",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            imported = AppConfig.import_profile(path)
            self.config_data = imported
            messagebox.showinfo("Imported", "Configuration imported. Please restart for full effect.")

    def _reset_settings(self) -> None:
        if messagebox.askyesno("Reset", "Reset all settings to defaults?"):
            self.config_data.reset_to_defaults()
            messagebox.showinfo("Reset", "Settings reset to defaults.")

    def _apply_settings_to_config(self) -> None:
        """Sync widget values into config_data."""
        self.config_data.recursive            = self._recursive_var.get()
        self.config_data.enable_categorization= self._cat_var.get()
        self.config_data.sentence_model       = self._st_model_var.get().strip()
        self.config_data.similarity_threshold = round(self._threshold_var.get(), 2)
        self.config_data.min_word_count       = self._min_words_var.get()
        self.config_data.whisper_model_size   = self._whisper_var.get()
        self.config_data.use_gpu              = self._gpu_var.get()
        self.config_data.max_workers          = self._workers_var.get()
        raw_excl = self._excl_var.get()
        self.config_data.excluded_extensions  = [
            e.strip().lower() for e in raw_excl.split(",") if e.strip()
        ]
        # Sync category checkboxes: empty list = process all
        if hasattr(self, "_cat_check_vars"):
            selected = [name for name, var in self._cat_check_vars.items() if var.get()]
            self.config_data.selected_categories = selected

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _toggle_theme(self) -> None:
        if self._colors is DARK:
            self.config_data.theme = "light"
            self._colors = LIGHT
        else:
            self.config_data.theme = "dark"
            self._colors = DARK
        self.config_data.save()
        # Full rebuild is the simplest correct approach for tkinter theme switching
        self._rebuild()

    def _rebuild(self) -> None:
        """Destroy and recreate the entire UI with the new colour palette."""
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(bg=self._colors["bg"])
        self._build_ui()
        self._switch_tab(self._active_tab)

    # ------------------------------------------------------------------
    # ttk style helpers
    # ------------------------------------------------------------------

    def _apply_treeview_style(self) -> None:
        c = self._colors
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure(
            "Treeview",
            background=c["surface2"],
            foreground=c["text"],
            fieldbackground=c["surface2"],
            rowheight=22,
            font=F_SMALL,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=c["surface"],
            foreground=c["text_dim"],
            font=(FONT_FAMILY, 9, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", c["accent"])],
            foreground=[("selected", "#ffffff")],
        )

    # ------------------------------------------------------------------
    # Widget factory helpers
    # ------------------------------------------------------------------

    def _make_labeled_entry(
        self,
        parent: tk.Widget,
        c: Dict[str, str],
        label: str,
        var: tk.Variable,
    ) -> tk.Entry:
        tk.Label(parent, text=label, font=F_LABEL,
                 fg=c["text_dim"], bg=c["surface"]).pack(anchor="w", pady=(6, 2))
        entry = tk.Entry(
            parent, textvariable=var,
            font=F_MONO, bg=c["surface2"], fg=c["text"],
            insertbackground=c["text"], relief="flat", bd=4,
            highlightthickness=1, highlightcolor=c["border"],
            highlightbackground=c["border"],
        )
        entry.pack(fill="x")
        return entry

    def _make_labeled_spinbox(
        self,
        parent: tk.Widget,
        c: Dict[str, str],
        label: str,
        var: tk.Variable,
        from_: int,
        to: int,
    ) -> ttk.Spinbox:
        tk.Label(parent, text=label, font=F_LABEL,
                 fg=c["text_dim"], bg=c["surface"]).pack(anchor="w", pady=(8, 2))
        sb = ttk.Spinbox(parent, from_=from_, to=to, textvariable=var,
                         width=6, font=F_LABEL)
        sb.pack(anchor="w")
        return sb


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def launch(config: Optional[AppConfig] = None) -> None:
    """
    Launch the ai_file GUI.

    Parameters
    ----------
    config:
        Optional pre-loaded ``AppConfig``.  If ``None``, the config is loaded
        from the default path (``config.json`` in the project root).
    """
    if config is None:
        config = AppConfig.load()

    app = App(config)
    app.mainloop()
