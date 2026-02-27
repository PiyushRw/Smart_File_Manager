# 📁 Smart File Organizer

A modern, AI-powered desktop application for organizing files intelligently using content analysis and semantic search.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

- 🤖 **AI-Powered Categorization**: Uses NLP and semantic analysis to understand file content
- 🎨 **Modern Dark UI**: Sleek interface built with CustomTkinter
- 🔍 **Smart Query System**: Organize files by custom categories (e.g., "Invoice", "Legal", "Medical")
- 📊 **Real-time Progress**: Animated progress bars and live status updates
- ⚡ **Multi-threaded**: Smooth UI with background processing
- 🎯 **Multiple File Types**: Supports documents, images, audio, video, and more
- 📈 **Category Breakdown**: Visual statistics of organized files
- ⏱️ **Time Tracking**: Shows elapsed time and estimated completion

## 🖼️ Screenshots

### Main Interface
- Clean, modern dark theme
- Easy folder selection
- Optional smart query input
- Real-time status updates

### Settings Panel
- Toggle default organizer
- Duplicate file handling
- Move or copy mode

## 📋 Requirements

- Python 3.8 or higher
- At least 4GB RAM (for AI models)
- Windows, macOS, or Linux

## 🚀 Installation

### Step 1: Clone or Download

```bash
git clone <your-repo-url>
cd <repo-name>
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Download spaCy Model

```bash
python -m spacy download en_core_web_sm
```

### Step 5: Run the Application

```bash
python ui.py
```

## 📖 Usage Guide

### Basic Usage

1. **Launch the app**: Run `python ui.py`
2. **Select folder**: Click "📂 Browse" and choose the folder you want to organize
3. **Optional query**: Enter a smart query like "organize by Invoice, Legal, Medical"
4. **Click "Start Organizing"**: The app will:
   - Scan all files
   - Analyze content with AI
   - Apply semantic matching (if query provided)
   - Organize files into categories
   - Show detailed statistics

### Settings

Click the **⚙️ Settings** button to configure:

- **Default Organizer**: Use simple file extension categorization (faster)
- **Check Duplicates**: Automatically rename duplicate files
- **File Action**: 
  - **Move**: Cut files from source folder (default)
  - **Copy**: Keep originals, copy to organized folder

### Smart Query Examples

- `"organize by Invoice, Contract, Legal"`
- `"sort by Medical, Financial, Personal"`
- `"categorize as Resume, Portfolio, Certificate"`

Leave the query empty for automatic AI categorization.

## 🔧 How It Works

### 1. File Scanning
- Walks through the selected folder
- Identifies file types by extension
- Extracts content from:
  - **Documents**: PDF, DOCX, TXT, CSV, XLSX
  - **Images**: OCR text extraction
  - **Audio/Video**: Speech-to-text transcription (first 2.5 minutes)

### 2. AI Categorization
- Uses spaCy NLP to extract keywords
- Identifies dominant topics in each file
- Creates intelligent categories based on content

### 3. Semantic Matching (Optional)
- Uses Sentence Transformers for semantic similarity
- Compares file keywords against your custom categories
- Refines categorization based on query

### 4. Organization
- Creates category folders
- Moves or copies files
- Handles duplicates automatically
- Preserves file metadata

## 📊 Supported File Types

| Category | Extensions |
|----------|-----------|
| **Documents** | .pdf, .docx, .doc, .txt, .md, .xlsx, .csv, .pptx |
| **Images** | .jpg, .jpeg, .png, .bmp, .gif, .tiff, .webp |
| **Audio** | .mp3, .wav, .flac, .m4a, .aac |
| **Video** | .mp4, .mov, .mkv, .avi, .webm |
| **Archives** | .zip, .rar, .7z, .tar, .gz |
| **Executables** | .exe, .msi, .bat, .sh, .app |
| **Code** | .py, .js, .html, .css, .java, .cpp |

## ⚙️ Configuration

### Performance Tuning

For large folders (1000+ files), consider:

1. **Enable Default Organizer** in settings (faster, skips AI analysis)
2. **Close other applications** to free up RAM
3. **Process in batches** by organizing subfolders separately

### Model Selection

The app uses these AI models:
- **spaCy**: `en_core_web_sm` (small, fast)
- **Sentence Transformer**: `all-MiniLM-L6-v2` (lightweight)
- **Whisper**: `base` model (speech recognition)

For better accuracy, you can modify `file_organizer_complete.py` to use larger models.

## 🐛 Troubleshooting

### Issue: "Module not found"
```bash
# Make sure you're in the virtual environment
pip install -r requirements.txt
```

### Issue: "spaCy model not found"
```bash
python -m spacy download en_core_web_sm
```

### Issue: UI not responding
- The app uses threading, but very large files (>500MB video) may cause delays
- Try enabling "Default Organizer" in settings
- Process smaller batches

### Issue: OCR/Whisper errors
- EasyOCR requires internet connection on first run (downloads models)
- Whisper models are downloaded automatically
- Check your internet connection

## 📝 Notes

- **First run**: The app will download AI models (may take a few minutes)
- **Performance**: Processing time depends on:
  - Number of files
  - File sizes
  - File types (videos take longer)
  - CPU/RAM available
- **Safety**: The app doesn't delete files, only moves/copies them
- **Backup**: Always keep backups of important files before organizing

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## 📄 License

MIT License - feel free to use for personal or commercial projects

## 🙏 Credits

Built with:
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern UI
- [spaCy](https://spacy.io/) - NLP
- [Sentence Transformers](https://www.sbert.net/) - Semantic search
- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - OCR
- [Faster Whisper](https://github.com/guillaumekln/faster-whisper) - Speech-to-text
- [MarkItDown](https://github.com/microsoft/markitdown) - Document conversion

## 📧 Support

If you encounter issues or have questions, please open an issue on GitHub.

---

Made with ❤️ for better file organization
