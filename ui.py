import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
from datetime import timedelta
import os
from logic import (
    scan_folder, 
    refine_categories_with_semantic_search,
    organize_files_into_folders,
    extract_keywords_from_preview,
    get_categories_from_query
)
import pandas as pd

# Set appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AnimatedProgressBar(ctk.CTkFrame):
    """Custom animated progress bar with gradient effect"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate")
        self.progress.pack(fill="x", padx=10, pady=5)
        
        self.label = ctk.CTkLabel(self, text="", font=("Roboto", 11))
        self.label.pack(pady=(0, 5))
        
        self.is_running = False
    
    def start(self, message="Processing..."):
        """Start the animated progress bar"""
        self.label.configure(text=message)
        self.progress.start()
        self.is_running = True
    
    def stop(self):
        """Stop the animated progress bar"""
        self.progress.stop()
        self.is_running = False
        self.label.configure(text="")


class SettingsWindow(ctk.CTkToplevel):
    """Settings window - REMOVED move/copy option, only subfolder toggle remains"""
    def __init__(self, parent, settings_dict):
        super().__init__(parent)
        
        self.title("Settings")
        self.geometry("450x220")  # Reduced height since we removed action mode
        self.resizable(False, False)
        
        # Make it modal
        self.transient(parent)
        self.grab_set()
        
        # Center the window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.winfo_screenheight() // 2) - (220 // 2)
        self.geometry(f"+{x}+{y}")
        
        self.settings_dict = settings_dict
        
        self._create_widgets()
    
    def _create_widgets(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            header_frame,
            text="⚙️ Settings",
            font=("Roboto", 24, "bold")
        ).pack(anchor="w")
        
        # Settings content
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Include Subfolders Toggle
        subfolders_frame = ctk.CTkFrame(content_frame, fg_color="#2b2b2b", corner_radius=10)
        subfolders_frame.pack(fill="x", pady=10)
        
        subfolders_inner = ctk.CTkFrame(subfolders_frame, fg_color="transparent")
        subfolders_inner.pack(fill="x", padx=15, pady=15)
        
        left_frame = ctk.CTkFrame(subfolders_inner, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True)
        
        ctk.CTkLabel(
            left_frame,
            text="Include Subfolders",
            font=("Roboto", 14, "bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            left_frame,
            text="Scan files in subdirectories too",
            font=("Roboto", 11),
            text_color="#888888"
        ).pack(anchor="w")
        
        self.include_subfolders_switch = ctk.CTkSwitch(
            subfolders_inner,
            text="",
            onvalue=True,
            offvalue=False
        )
        self.include_subfolders_switch.pack(side="right")
        
        if self.settings_dict.get("include_subfolders", True):
            self.include_subfolders_switch.select()
        
        # Info about automatic workflow
        info_frame = ctk.CTkFrame(content_frame, fg_color="#1e3a28", corner_radius=10)
        info_frame.pack(fill="x", pady=10)
        
        info_inner = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_inner.pack(fill="x", padx=15, pady=12)
        
        ctk.CTkLabel(
            info_inner,
            text="ℹ️  File Organization Mode",
            font=("Roboto", 13, "bold"),
            text_color="#88ff88"
        ).pack(anchor="w", pady=(0, 5))
        
        ctk.CTkLabel(
            info_inner,
            text="Automatic: Copy → Verify → Delete originals\nYour files are safe - originals only deleted after verification.",
            font=("Roboto", 10),
            text_color="#cccccc",
            justify="left"
        ).pack(anchor="w")
        
        # Save button
        ctk.CTkButton(
            self,
            text="Save Settings",
            command=self._save_settings,
            height=40,
            font=("Roboto", 13, "bold")
        ).pack(pady=20, padx=20, fill="x")
    
    def _save_settings(self):
        """Save settings and close window"""
        self.settings_dict["include_subfolders"] = self.include_subfolders_switch.get()
        self.destroy()


class FileOrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window configuration
        self.title("Smart File Organizer")
        self.geometry("900x720")  # Reduced from 750 to 720
        self.minsize(800, 620)    # Reduced from 650 to 620
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.winfo_screenheight() // 2) - (720 // 2)  # Updated for new height
        self.geometry(f"+{x}+{y}")
        
        # Settings dictionary (removed action setting - always automatic copy-verify-delete)
        self.settings = {
            "include_subfolders": True
        }
        
        # State variables
        self.selected_folder = None
        self.is_processing = False
        self.df_result = None
        self.extracted_categories = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        # Main container
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # ========== HEADER ==========
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))
        
        # Title
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(side="left")
        
        ctk.CTkLabel(
            title_frame,
            text="📁 Smart File Organizer",
            font=("Roboto", 28, "bold")
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            title_frame,
            text="AI-powered file organization • Auto Copy-Verify-Delete",
            font=("Roboto", 12),
            text_color="#888888"
        ).pack(anchor="w")
        
        # Settings button
        self.settings_btn = ctk.CTkButton(
            header_frame,
            text="⚙️ Settings",
            command=self._open_settings,
            width=120,
            height=40,
            font=("Roboto", 13, "bold"),
            fg_color="#2b2b2b",
            hover_color="#3b3b3b"
        )
        self.settings_btn.pack(side="right")
        
        # ========== FOLDER SELECTION ==========
        folder_frame = ctk.CTkFrame(main_container, fg_color="#2b2b2b", corner_radius=15)
        folder_frame.pack(fill="x", pady=(0, 15))
        
        folder_inner = ctk.CTkFrame(folder_frame, fg_color="transparent")
        folder_inner.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(
            folder_inner,
            text="Source Folder",
            font=("Roboto", 14, "bold")
        ).pack(anchor="w", pady=(0, 10))
        
        folder_select_frame = ctk.CTkFrame(folder_inner, fg_color="transparent")
        folder_select_frame.pack(fill="x")
        
        self.folder_entry = ctk.CTkEntry(
            folder_select_frame,
            placeholder_text="No folder selected",
            height=40,
            font=("Roboto", 12),
            state="readonly"
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.browse_btn = ctk.CTkButton(
            folder_select_frame,
            text="📂 Browse",
            command=self._browse_folder,
            width=120,
            height=40,
            font=("Roboto", 13, "bold")
        )
        self.browse_btn.pack(side="right")
        
        # ========== QUERY INPUT ==========
        query_frame = ctk.CTkFrame(main_container, fg_color="#2b2b2b", corner_radius=15)
        query_frame.pack(fill="x", pady=(0, 15))
        
        query_inner = ctk.CTkFrame(query_frame, fg_color="transparent")
        query_inner.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(
            query_inner,
            text="Smart Query (Optional)",
            font=("Roboto", 14, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        ctk.CTkLabel(
            query_inner,
            text="e.g., 'organize by Invoice, Legal, Medical' or leave empty for auto-categorization",
            font=("Roboto", 11),
            text_color="#888888"
        ).pack(anchor="w", pady=(0, 10))
        
        # Query input with send button
        query_input_frame = ctk.CTkFrame(query_inner, fg_color="transparent")
        query_input_frame.pack(fill="x", pady=(0, 10))
        
        self.query_entry = ctk.CTkEntry(
            query_input_frame,
            placeholder_text="Enter your organization query...",
            height=40,
            font=("Roboto", 12)
        )
        self.query_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # Bind Enter key to send query
        self.query_entry.bind("<Return>", lambda e: self._send_query())
        
        self.send_query_btn = ctk.CTkButton(
            query_input_frame,
            text="🔍 Analyze",
            command=self._send_query,
            width=120,
            height=40,
            font=("Roboto", 13, "bold"),
            fg_color="#1f6aa5",
            hover_color="#144870"
        )
        self.send_query_btn.pack(side="right")
        
        # Extracted categories display
        self.categories_display_frame = ctk.CTkFrame(query_inner, fg_color="#1e1e1e", corner_radius=10)
        self.categories_display_frame.pack(fill="x")
        self.categories_display_frame.pack_forget()  # Hidden initially
        
        categories_inner = ctk.CTkFrame(self.categories_display_frame, fg_color="transparent")
        categories_inner.pack(fill="x", padx=15, pady=12)
        
        self.categories_label = ctk.CTkLabel(
            categories_inner,
            text="",
            font=("Roboto", 11),
            text_color="#88ff88",
            anchor="w",
            justify="left"
        )
        self.categories_label.pack(fill="x")
        
        # ========== PROGRESS SECTION ==========
        self.progress_frame = ctk.CTkFrame(main_container, fg_color="#2b2b2b", corner_radius=15, height=300)
        self.progress_frame.pack(fill="x", expand=False, pady=(0, 10))  # Changed to expand=False and fill="x"
        self.progress_frame.pack_propagate(False)  # Prevent children from expanding the frame
        
        progress_inner = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        progress_inner.pack(fill="both", expand=True, padx=20, pady=15)  # Reduced padding from 20 to 15
        
        # Progress header
        progress_header = ctk.CTkFrame(progress_inner, fg_color="transparent")
        progress_header.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            progress_header,
            text="Status",
            font=("Roboto", 14, "bold")
        ).pack(side="left")
        
        self.time_label = ctk.CTkLabel(
            progress_header,
            text="",
            font=("Roboto", 11),
            text_color="#888888"
        )
        self.time_label.pack(side="right")
        
        # Animated progress bar
        self.progress_bar = AnimatedProgressBar(progress_inner, fg_color="transparent")
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar.pack_forget()  # Hide initially
        
        # Status text area (scrollable) - FIXED: Don't use expand=True
        self.status_text = ctk.CTkTextbox(
            progress_inner,
            font=("Consolas", 11),
            fg_color="#1e1e1e",
            wrap="word",
            state="disabled",
            height=180  # Reduced from 200 to 180 to ensure button visibility
        )
        self.status_text.pack(fill="x", expand=False)  # Changed expand=False
        
        self._add_status("Ready to organize files. Select a folder to begin.", "info")
        self._add_status("Mode: Automatic Copy → Verify → Delete originals (safe)", "info")
        
        # ========== ACTION BUTTON ==========
        button_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))  # Increased top padding
        
        self.organize_btn = ctk.CTkButton(
            button_frame,
            text="🚀 Start Organizing (Copy-Verify-Delete)",
            command=self._start_organizing,
            height=50,
            font=("Roboto", 16, "bold"),
            text_color="white",
            state="disabled"
        )
        self.organize_btn.pack(fill="x", padx=0, pady=0)
    
    def _open_settings(self):
        """Open settings window"""
        SettingsWindow(self, self.settings)
    
    def _browse_folder(self):
        """Browse and select folder"""
        folder = filedialog.askdirectory(title="Select Folder to Organize")
        if folder:
            self.selected_folder = folder
            self.folder_entry.configure(state="normal")
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)
            self.folder_entry.configure(state="readonly")
            self.organize_btn.configure(state="normal")
            self._add_status(f"Selected folder: {folder}", "success")
    
    def _send_query(self):
        """Process and validate the query, showing extracted categories"""
        query = self.query_entry.get().strip()
        
        if not query:
            # Clear display if query is empty
            self.categories_display_frame.pack_forget()
            self.extracted_categories = None
            self._add_status("⚠️ Query cleared - will use auto-categorization", "info")
            return
        
        # Extract categories from query
        try:
            categories = get_categories_from_query(query)
            
            if not categories:
                # No valid categories found
                self.categories_display_frame.pack_forget()
                self.extracted_categories = None
                self._add_status("⚠️ No valid categories found in query. Try: 'organize by Invoice, Legal, Medical'", "warning")
                messagebox.showwarning(
                    "Invalid Query",
                    "Could not extract categories from your query.\n\n"
                    "Try using nouns like:\n"
                    "• 'organize by Invoice, Legal, Medical'\n"
                    "• 'sort by Resume, Portfolio, Certificate'\n"
                    "• 'categorize as Financial, Personal, Work'"
                )
            else:
                # Valid categories found - show them
                self.extracted_categories = categories
                
                # Format categories for display
                category_text = "✓ Categories detected: " + ", ".join([f"'{cat}'" for cat in categories])
                self.categories_label.configure(text=category_text)
                
                # Show the display frame
                self.categories_display_frame.pack(fill="x", pady=(0, 0))
                
                # Log to status
                self._add_status(f"✅ Query analyzed - found {len(categories)} categories: {', '.join(categories)}", "success")
                
        except Exception as e:
            self.categories_display_frame.pack_forget()
            self.extracted_categories = None
            self._add_status(f"❌ Error analyzing query: {str(e)}", "error")
    
    def _add_status(self, message, type="info"):
        """Add status message to text area (thread-safe)"""
        def update():
            self.status_text.configure(state="normal")
            
            # Color coding
            colors = {
                "info": "#88ccff",
                "success": "#88ff88",
                "warning": "#ffcc88",
                "error": "#ff8888"
            }
            
            tag_name = f"{type}_{time.time()}"
            
            timestamp = time.strftime("%H:%M:%S")
            full_message = f"[{timestamp}] {message}\n"
            
            self.status_text.insert("end", full_message, tag_name)
            self.status_text.tag_config(tag_name, foreground=colors.get(type, "#ffffff"))
            self.status_text.see("end")
            self.status_text.configure(state="disabled")
        
        if threading.current_thread() != threading.main_thread():
            self.after(0, update)
        else:
            update()
    
    def _clear_status(self):
        """Clear status text area"""
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.configure(state="disabled")
    
    def _update_time_label(self, elapsed_time):
        """Update elapsed time label"""
        def update():
            delta = timedelta(seconds=int(elapsed_time))
            self.time_label.configure(text=f"⏱️ Elapsed: {delta}")
        
        self.after(0, update)
    
    def _start_organizing(self):
        """Start the organization process in a separate thread"""
        if not self.selected_folder:
            messagebox.showwarning("No Folder", "Please select a folder first!")
            return
        
        if self.is_processing:
            messagebox.showinfo("Processing", "Already processing files...")
            return
        
        # Show confirmation dialog explaining the workflow
        response = messagebox.askyesno(
            "Confirm Organization",
            "This will:\n"
            "1. Copy all files to organized folders\n"
            "2. Verify copied files\n"
            "3. Delete original files (only if verification passes)\n\n"
            "Your files are safe - originals won't be deleted unless\n"
            "all copies are verified successfully.\n\n"
            "Continue?"
        )
        
        if not response:
            return
        
        # Disable buttons
        self.organize_btn.configure(state="disabled", text="⏳ Processing...", text_color="white")
        self.browse_btn.configure(state="disabled")
        self.settings_btn.configure(state="disabled")
        self.send_query_btn.configure(state="disabled")
        
        # Clear and prepare UI
        self._clear_status()
        self.progress_bar.pack(fill="x", pady=(0, 15))
        self.progress_bar.start("Initializing...")
        
        # Start processing in thread
        thread = threading.Thread(target=self._organize_files_thread, daemon=True)
        thread.start()
    
    def _organize_files_thread(self):
        """Main organization logic (runs in separate thread)"""
        self.is_processing = True
        start_time = time.time()
        
        try:
            # Step 1: Scan folder
            self._add_status("=" * 60, "info")
            subfolder_msg = "including subfolders" if self.settings["include_subfolders"] else "top-level only"
            self._add_status(f"📂 STEP 1: Scanning folder ({subfolder_msg})...", "info")
            self.after(0, lambda: self.progress_bar.start("📂 Scanning folder..."))
            
            # Define progress callback for real-time updates
            def scan_callback(msg):
                self._add_status(msg, "info")
            
            df = scan_folder(
                self.selected_folder, 
                progress_callback=scan_callback,
                include_subfolders=self.settings["include_subfolders"]
            )
            
            elapsed = time.time() - start_time
            self._update_time_label(elapsed)
            self._add_status(f"✅ Found {len(df)} files", "success")
            
            if len(df) == 0:
                self._add_status("⚠️ No files found in the selected folder", "warning")
                self._finish_processing()
                return
            
            # Step 2: Category Assignment
            time.sleep(0.5)
            self._add_status("=" * 60, "info")
            
            user_query = self.query_entry.get().strip()
            
            if user_query:
                # Query provided → Match to query categories
                self._add_status("🎯 STEP 2: Matching files to query categories...", "info")
                
                # Show which categories will be used
                if self.extracted_categories:
                    self._add_status(f"   Categories: {', '.join(self.extracted_categories)}", "info")
                else:
                    self._add_status("⚠️ Query not analyzed - analyzing now...", "warning")
                
                self.after(0, lambda: self.progress_bar.start("🔍 Semantic matching..."))
                
                # Progress callback for semantic search
                def semantic_callback(msg):
                    self._add_status(msg, "info")
                
                df = refine_categories_with_semantic_search(df, user_query, progress_callback=semantic_callback)
                
                elapsed = time.time() - start_time
                self._update_time_label(elapsed)
                self._add_status("✅ Query-based categorization complete", "success")
            else:
                # No query → Use extension-based categories
                self._add_status("📋 STEP 2: Using extension-based categories", "info")
                self._add_status("   (Documents, Images, Videos, Audio, etc.)", "info")
            
            # Display category breakdown
            time.sleep(0.5)
            self._add_status("=" * 60, "info")
            self._add_status("📊 CATEGORY BREAKDOWN:", "info")
            
            category_counts = df['Category'].value_counts()
            for category, count in category_counts.items():
                self._add_status(f"   • {category}: {count} files", "success")
            
            # Step 3: Organize files (automatic copy-verify-delete)
            time.sleep(0.5)
            self._add_status("=" * 60, "info")
            
            destination = os.path.join(
                os.path.dirname(self.selected_folder),
                "Organized_Files"
            )
            
            self._add_status(f"📦 STEP 3: Organizing files → {destination}", "info")
            self._add_status("   Workflow: Copy → Verify → Delete originals", "info")
            self.after(0, lambda: self.progress_bar.start("📦 Copying and organizing..."))
            
            # Progress callback for file organization
            def organize_callback(msg):
                self._add_status(msg, "info")
            
            # NOTE: No action parameter - function always does copy-verify-delete
            organize_files_into_folders(df, destination, progress_callback=organize_callback)
            
            elapsed = time.time() - start_time
            self._update_time_label(elapsed)
            
            # Success message
            self._add_status("=" * 60, "success")
            self._add_status("✅ ORGANIZATION COMPLETE!", "success")
            self._add_status(f"⏱️  Total time: {timedelta(seconds=int(elapsed))}", "success")
            self._add_status(f"📁 Files organized in: {destination}", "success")
            self._add_status("=" * 60, "success")
            
            # Show success dialog
            self.after(0, lambda: messagebox.showinfo(
                "Success!",
                f"Successfully organized {len(df)} files!\n\n"
                f"Location: {destination}\n"
                f"Time: {timedelta(seconds=int(elapsed))}\n\n"
                f"All files were copied, verified, and originals deleted."
            ))
            
        except Exception as e:
            self._add_status(f"❌ ERROR: {str(e)}", "error")
            self.after(0, lambda: messagebox.showerror("Error", f"An error occurred:\n{str(e)}"))
        
        finally:
            self._finish_processing()
    
    def _finish_processing(self):
        """Clean up after processing"""
        def cleanup():
            self.is_processing = False
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.organize_btn.configure(state="normal", text="🚀 Start Organizing (Copy-Verify-Delete)", text_color="white")
            self.browse_btn.configure(state="normal")
            self.settings_btn.configure(state="normal")
            self.send_query_btn.configure(state="normal")
            self.time_label.configure(text="")
        
        self.after(0, cleanup)


def main():
    app = FileOrganizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()