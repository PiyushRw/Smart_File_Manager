# 🗂 Smart File Manager

An intelligent, AI-powered file organiser that automatically sorts your files using **extension-based categorisation** and **semantic NLP matching** — with a modern dark/light GUI.

---

## ✨ Features

- **Auto-categorisation** — sorts files into folders like `Documents`, `Images`, `Videos`, `Code`, etc. by extension
- **Semantic search** — type a query like `"financial reports 2024"` and matching files are grouped into named sub-folders
- **Smart 3-step matching** — checks filename → start/end content snippet → full NLP (fast & accurate)
- **20+ file formats** — PDF, DOCX, PPTX, XLSX, CSV, TXT, HTML, XML, JSON, images (OCR), audio & video (transcription)
- **GPU acceleration** — CUDA support for EasyOCR, Whisper, and SentenceTransformer
- **Safe file moves** — copy → verify size → delete original (no data loss)
- **Pause / Resume / Cancel** — full run control from the GUI
- **Dark & Light theme** — modern themed tkinter UI
- **CLI mode** — run headless for automation/scripting

---

## 🖥 Screenshots

> GUI launches with `python run.py`

---

## 🚀 Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/PiyushRw/Smart_File_Manager.git
cd Smart_File_Manager
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Download the spaCy model
```bash
python -m spacy download en_core_web_sm
```

### 4. Run
```bash
# GUI mode
python run.py

# CLI mode
python run.py --cli \
  --source "C:\path\to\messy\folder" \
  --output "C:\path\to\organised" \
  --query "financial reports invoices 2024"
```

---

## 📦 CLI Options

| Flag | Description |
|---|---|
| `--cli` | Run headless (no GUI) |
| `--source PATH` | Source folder to scan (repeat for multiple) |
| `--output PATH` | Destination root folder |
| `--query TEXT` | Semantic keyword query for sub-folder grouping |
| `--no-recursive` | Don't scan sub-folders |
| `--no-categorize` | Disable automatic file-type categorisation |
| `--workers N` | Number of parallel threads (default: 4) |
| `--config PATH` | Path to a custom JSON config file |
| `--log-file PATH` | Also write logs to a file |
| `--debug` | Enable verbose DEBUG logging |

---

## 🗃 Supported File Types

| Category | Extensions |
|---|---|
| Documents | `.pdf` `.docx` `.doc` `.txt` `.md` `.odt` `.rtf` `.tex` |
| Spreadsheets | `.xlsx` `.xls` `.csv` `.ods` |
| Presentations | `.pptx` `.ppt` `.odp` |
| Images | `.jpg` `.jpeg` `.png` `.bmp` `.gif` `.webp` `.tiff` `.svg` `.heic` |
| Videos | `.mp4` `.avi` `.mov` `.mkv` `.wmv` `.flv` `.webm` |
| Audio | `.mp3` `.wav` `.m4a` `.flac` `.ogg` `.aac` |
| Archives | `.zip` `.tar` `.gz` `.7z` `.rar` |
| Code | `.py` `.js` `.ts` `.java` `.c` `.cpp` `.go` `.rs` `.sh` |
| Web | `.html` `.htm` `.xml` `.json` `.yaml` `.css` |
| Email | `.eml` `.msg` |
| Databases | `.sql` `.db` `.sqlite` |
| Fonts | `.ttf` `.otf` `.woff` `.woff2` |
| Executables | `.exe` `.msi` `.apk` `.dmg` |

---

## 🧠 How Semantic Matching Works

```
For each file (when a query is set):

  Step 1 — Filename only         (free, no disk read)
            "annual_report_2024" → extract noun phrases → similarity check
            ✓ match found → done

  Step 2+3 — Extract text → smart sample
            first 500 chars (title/intro) + last 200 chars (conclusion)
            → extract noun phrases → similarity check
            ✓ match → keyword sub-folder
            ✗ no match → category folder
```

---

## ⚙️ Configuration

All settings are saved in `config.json` and editable via the GUI Settings tab.

Key settings:

| Setting | Default | Description |
|---|---|---|
| `similarity_threshold` | `0.45` | Min cosine similarity for a keyword match (0–1) |
| `sentence_model` | `all-MiniLM-L6-v2` | HuggingFace embedding model |
| `whisper_model_size` | `base` | Whisper model for audio/video |
| `recursive` | `true` | Scan sub-folders |
| `copy_then_delete` | `true` | Safe move strategy |
| `max_workers` | `4` | Parallel threads |

---

## 📋 Requirements

- Python 3.10+
- See [`requirements.txt`](requirements.txt) for full list

### Optional (for GPU acceleration)
```bash
# CUDA 12.1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

---

## 📁 Project Structure

```
smart_file_manager/
├── run.py           ← Entry point
├── __init__.py      ← Package API
├── config.py        ← Settings (AppConfig dataclass)
├── config.json      ← Persisted user settings
├── categorizer.py   ← Extension → Category mapping
├── extractor.py     ← Text extraction (20+ formats)
├── utils.py         ← Logging, GPU detection, ML model singletons
├── logic.py         ← Core pipeline (scan → extract → match → move)
├── gui.py           ← tkinter GUI
└── requirements.txt
```

---

## 📄 License

MIT License — feel free to use, modify, and distribute.
