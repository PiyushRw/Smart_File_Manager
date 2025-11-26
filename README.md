# 📁 AI-Powered File Organizer (Deep Learning Edition)

An intelligent desktop application that automatically **classifies, categorizes, and organizes files** using AI and deep learning.  
Built with **Python, TensorFlow, Tkinter, FAISS-like classification logic, and smart rule-based detection**.

🔍 Automatically identifies file types  
🧠 Uses MobileNetV2 for optional image classification  
📂 Organizes files into meaningful categories  
📊 Provides visual statistics and real-time progress  
🎨 Modern dark-themed, professional GUI  

---

## 🚀 Features

### ✓ AI-Based File Classification  
- Uses **MobileNetV2** to classify image files for deeper accuracy  
- Extension-based smart classification for documents, audio, video, archives, code, and more  
- Categorization mapping: Images, Videos, Documents, Audio, Archives, Code, Data, Executables, etc. :contentReference[oaicite:1]{index=1}

### ✓ Intelligent File Organization  
- Automatically creates category subfolders  
- Moves files into correct folders safely  
- Handles duplicates gracefully  
- Supports large folders and nested directories  
- Logs every operation in real time

### ✓ Modern Graphical Interface  
- Built using **Tkinter** with a sleek dark theme  
- Live progress bar and processing count  
- Activity log terminal  
- Interactive pie-chart and bar-chart analytics using **Matplotlib**  
- Settings page with configurable options

---

## 🛠️ Technologies Used

- **Python 3.x**
- **TensorFlow / Keras — MobileNetV2, EfficientNet (optional)**  
- **Tkinter** — GUI  
- **Matplotlib** — Visualization  
- **NumPy / Pandas** — Data handling  
- **Scikit-learn** — Preprocessing utilities  
- **PIL (Pillow)** — Image processing  
- **Shutil / OS / Pathlib** — File operations  
- **Threading** — Background file processing  

---

## 📂 Project Structure
.
├── file_organizer.py
├── README.md # 

---

## ▶️ How to Run

### 1. Install dependencies:

pip install tensorflow pillow matplotlib pandas numpy scikit-learn

 
### 2. Run the application:

python file_organizer.py

🧠 How It Works
1. Classification Engine

The DeepLearningClassifier intelligently categorizes files by:

Checking the file extension against predefined category mappings

Optionally classifying images using MobileNetV2 for deeper semantic detection

Falling back to “Other” for unknown file types


file_organizer

2. AI-Assisted File Organization

The FileOrganizer moves files into subfolders based on classification and logs each operation:

Handles collisions by renaming duplicates

Tracks number of files per category

Generates a full organization report


file_organizer

3. Professional GUI

FileOrganizerGUI provides:

Directory picker

Real-time progress updates

Activity log window

Pie chart and bar chart summary

Configurable settings such as enabling/disabling subfolder creation


🗂️ Supported File Types
Images

.jpg, .jpeg, .png, .gif, .bmp, .svg, .webp, .tiff

Documents

.pdf, .docx, .txt, .xls, .ppt, etc.

Videos, Audio, Archives, Code, Data, Executables

(mp4, mp3, zip, py, js, csv, exe, etc.)
— Fully configurable via the category mapping in the source code.

📌 Future Enhancements (Ideas)

Add FAISS vector indexing for semantic file similarity

Add cloud backup integration

Add face/object recognition for photo files

Add scheduling for auto-cleanup

Add drag-and-drop UI support
