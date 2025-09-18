import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
import time
import fitz  # PyMuPDF
from pathlib import Path
import torch
import re
import traceback
import torch.serialization
import sys
import subprocess
import shutil

# --- Add the necessary imports for the real TTS library ---
try:
    from TTS.api import TTS
    # --- Import the specific config classes needed for the fix ---
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig
except ImportError:
    messagebox.showerror("Critical Error", "TTS library not found. Please run 'pip install TTS' in your virtual environment.")
    sys.exit()

# --- Refactored to a more generic TTSEngine class ---
class TTSEngine:
    def __init__(self, model_name):
        self.model_name = model_name
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.check_installation()

    def check_installation(self):
        """Checks if essential libraries are installed."""
        try:
            import torch
            from TTS.api import TTS
            print("All necessary libraries (PyTorch, TTS) are installed.")
        except ImportError as e:
            messagebox.showerror("Installation Error", f"A required library is missing: {e}. Please ensure you are in the correct virtual environment and have run 'pip install -r requirements.txt'.")
            raise

    def load_model(self):
        """Loads the specified TTS model into memory. This can take time."""
        print(f"Using device: {self.device}")
        if self.device == "cpu":
            print("CUDA (GPU) not available. Falling back to CPU. Processing will be slower.")
        
        if "xtts" in self.model_name:
            print("Allowlisting XTTS-v2 configurations for safe loading...")
            torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])

        print(f"Loading TTS model: {self.model_name}. This may take a moment...")
        self.model = TTS(self.model_name).to(self.device)
        print("Model loaded successfully.")
        
        if self.model.is_multi_speaker and hasattr(self.model, 'speakers'):
            return self.model.speakers
        return None

    def tts(self, text, output_path, speaker_id=None, speaker_wav_path=None):
        """
        Performs text-to-speech conversion. The TTS library handles sentence splitting internally.
        """
        if not self.model:
            raise RuntimeError("TTS model is not loaded. Please load the model first.")

        print(f"Converting text to speech...")
        
        try:
            self.model.tts_to_file(
                text=text,
                speaker=speaker_id,
                speaker_wav=speaker_wav_path,
                language="en", 
                file_path=output_path
            )
            print("Conversion successful.")
        except Exception as e:
            print(f"An error occurred during TTS conversion: {e}")
            raise

class PDFConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kokoro - PDF to MP3 Converter")
        self.root.geometry("850x750")

        self.settings_file = "settings.json"
        self.pdf_queue = []
        self.destination_folder = str(Path.home() / "Downloads")
        self.is_running = False
        self.is_paused = False
        self.conversion_thread = None
        
        self.available_tts_models = {
            "VCTK (Multi-Voice)": "tts_models/en/vctk/vits",
            "XTTS-v2 (High Quality)": "tts_models/multilingual/multi-dataset/xtts_v2"
        }
        
        self.selected_tts_model = tk.StringVar()
        self.selected_voice = tk.StringVar()
        self.speaker_wav_path = tk.StringVar()
        self.optimize_mp3 = tk.BooleanVar(value=True)
        
        self.tts_engine = None

        self.load_settings()
        
        self.setup_ui()
        self.update_pdf_list()
        self.log("Application started. Please select and load a TTS model.")
        self.check_ffmpeg()

    def check_ffmpeg(self):
        """Checks if ffmpeg is installed and in the system's PATH."""
        if shutil.which("ffmpeg"):
            self.log("FFmpeg found. MP3 optimization is available.")
        else:
            self.log("WARNING: FFmpeg not found. The 'Optimize MP3' feature will be disabled.")
            self.optimize_mp3.set(False)
            if hasattr(self, 'optimize_checkbox'):
                self.optimize_checkbox.config(state="disabled")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        model_frame = ttk.Frame(main_frame, padding=(0, 0, 0, 10))
        model_frame.pack(fill="x")
        
        ttk.Label(model_frame, text="TTS Model:").pack(side="left", padx=(0, 5))
        self.model_dropdown = ttk.Combobox(model_frame, textvariable=self.selected_tts_model, values=list(self.available_tts_models.keys()), state="readonly")
        self.model_dropdown.pack(side="left", padx=(0, 10), fill="x", expand=True)
        self.model_dropdown.bind("<<ComboboxSelected>>", self.on_model_select)
        
        self.load_model_button = ttk.Button(model_frame, text="Load Selected Model", command=self.threaded_load_model)
        self.load_model_button.pack(side="left")

        self.voice_frame = ttk.Frame(main_frame, padding=(0, 0, 0, 10))
        self.voice_frame.pack(fill="x")
        
        self.vctk_voice_label = ttk.Label(self.voice_frame, text="Select Voice:")
        self.vctk_voice_dropdown = ttk.Combobox(self.voice_frame, textvariable=self.selected_voice, state="disabled", width=30)
        
        self.xtts_voice_label = ttk.Label(self.voice_frame, text="Voice File (.wav):")
        self.xtts_voice_entry = ttk.Entry(self.voice_frame, textvariable=self.speaker_wav_path, state="readonly")
        self.xtts_voice_button = ttk.Button(self.voice_frame, text="Select Voice File", command=self.select_voice_file)

        dest_frame = ttk.Frame(main_frame)
        dest_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(dest_frame, text="Destination:").pack(side="left", padx=(0, 5))
        self.dest_entry = ttk.Entry(dest_frame)
        self.dest_entry.insert(0, self.destination_folder)
        self.dest_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(dest_frame, text="Select", command=self.select_destination).pack(side="left", padx=(5,0))

        optimize_frame = ttk.Frame(main_frame, padding=(0, 0, 0, 10))
        optimize_frame.pack(fill="x")
        self.optimize_checkbox = ttk.Checkbutton(optimize_frame, text="Optimize MP3 for Fast Opening (Requires FFmpeg)", variable=self.optimize_mp3)
        self.optimize_checkbox.pack(anchor="w")


        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        self.pdf_tree = ttk.Treeview(list_frame, columns=("Status", "Path", "File Name"), show="headings")
        self.pdf_tree.heading("Status", text="Status"); self.pdf_tree.column("Status", width=80, anchor="center")
        self.pdf_tree.heading("Path", text="Path"); self.pdf_tree.column("Path", width=250)
        self.pdf_tree.heading("File Name", text="File Name"); self.pdf_tree.column("File Name", width=200)
        self.pdf_tree.pack(side="left", fill="both", expand=True)
        list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.pdf_tree.yview)
        self.pdf_tree.configure(yscrollcommand=list_scrollbar.set)
        list_scrollbar.pack(side="right", fill="y")

        btn_list_frame = ttk.Frame(main_frame)
        btn_list_frame.pack(fill="x", pady=5)
        ttk.Button(btn_list_frame, text="Find PDFs", command=self.find_pdfs).pack(side="left", padx=2)
        ttk.Button(btn_list_frame, text="Move Up", command=lambda: self.move_item(-1)).pack(side="left", padx=2)
        ttk.Button(btn_list_frame, text="Move Down", command=lambda: self.move_item(1)).pack(side="left", padx=2)
        ttk.Button(btn_list_frame, text="Delete Selected", command=self.delete_selected_pdfs).pack(side="left", padx=2)

        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="both", expand=True, pady=(10, 0))
        control_frame = ttk.Frame(bottom_frame)
        control_frame.pack(pady=5)
        
        # --- CHANGE: Start button is now disabled by default ---
        self.start_button = ttk.Button(control_frame, text="Start", command=self.start_conversion, state="disabled")
        self.start_button.pack(side="left", padx=5)
        
        self.pause_button = ttk.Button(control_frame, text="Pause", command=self.pause_resume_conversion, state="disabled")
        self.pause_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_conversion, state="disabled")
        self.stop_button.pack(side="left", padx=5)

        console_frame = ttk.LabelFrame(bottom_frame, text="Console", padding="5")
        console_frame.pack(fill="both", expand=True, pady=(5,0))
        self.console = tk.Text(console_frame, height=10, state="disabled", bg="black", fg="lime green", wrap="word")
        self.console.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.on_model_select(None)

    def on_model_select(self, event):
        """Updates the UI based on the selected model."""
        model_key = self.selected_tts_model.get()
        
        for widget in self.voice_frame.winfo_children():
            widget.pack_forget()

        if "XTTS" in model_key:
            self.xtts_voice_label.pack(side="left", padx=(0, 5))
            self.xtts_voice_entry.pack(side="left", fill="x", expand=True)
            self.xtts_voice_button.pack(side="left", padx=(5, 0))
        elif "VCTK" in model_key:
            self.vctk_voice_label.pack(side="left", padx=(0, 5))
            self.vctk_voice_dropdown.pack(side="left", fill="x", expand=True)

    def select_voice_file(self):
        filepath = filedialog.askopenfilename(title="Select a Voice File", filetypes=(("WAV files", "*.wav"), ("All files", "*.*")))
        if filepath:
            self.speaker_wav_path.set(filepath)
            self.log(f"Selected voice file: {os.path.basename(filepath)}")

    def threaded_load_model(self):
        model_key = self.selected_tts_model.get()
        if not model_key:
            messagebox.showwarning("No Model Selected", "Please select a model from the dropdown first.")
            return
            
        model_path = self.available_tts_models[model_key]
        self.tts_engine = TTSEngine(model_path)
        
        self.load_model_button.config(state="disabled")
        self.model_dropdown.config(state="disabled")
        self.log(f"Model loading initiated for {model_key}...")
        
        load_thread = threading.Thread(target=self.load_model_task, daemon=True)
        load_thread.start()

    def load_model_task(self):
        """The actual task of loading the model. To be run in a thread."""
        try:
            speakers = self.tts_engine.load_model()
            self.root.after(0, lambda: self.update_model_status(True, speakers=speakers))
        except Exception as e:
            error_details = traceback.format_exc()
            print("--- EXCEPTION CAUGHT DURING MODEL LOAD ---")
            print(error_details)
            print("------------------------------------------")
            full_error_msg = f"An error occurred during model loading. Please see the console for the full traceback.\n\nError: {e}"
            self.root.after(0, lambda: self.update_model_status(False, error_msg=full_error_msg))

    def update_model_status(self, success, speakers=None, error_msg=None):
        self.load_model_button.config(state="normal")
        self.model_dropdown.config(state="readonly")
        if success:
            # --- CHANGE: Enable the start button on successful model load ---
            self.start_button.config(state="normal")
            self.log("TTS model loaded successfully.")
            if self.tts_engine.model.is_multi_speaker and speakers:
                formatted_voices = [f"Speaker {i+1} ({speaker_id})" for i, speaker_id in enumerate(speakers)]
                self.vctk_voice_dropdown.config(state="readonly", values=formatted_voices)
                saved_voice = self.selected_voice.get()
                if saved_voice and saved_voice in formatted_voices:
                    self.vctk_voice_dropdown.set(saved_voice)
                else:
                    self.vctk_voice_dropdown.set(formatted_voices[0])
                self.log(f"Found {len(speakers)} voices.")
            else:
                self.vctk_voice_dropdown.config(state="disabled", values=[])
                self.selected_voice.set("")
        else:
            # --- CHANGE: Ensure start button remains disabled on failure ---
            self.start_button.config(state="disabled")
            self.log(f"CRITICAL: Failed to load TTS model. Error: {error_msg}")
            messagebox.showerror("Model Load Error", f"Failed to load the TTS model. Please check the console for details.\n\nError: {error_msg}")

    def log(self, message):
        self.root.after(0, self._log, message)
    
    def _log(self, message):
        self.console.config(state="normal")
        self.console.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.console.see(tk.END)
        self.console.config(state="disabled")

    def find_pdfs(self):
        directory = filedialog.askdirectory(title="Select Folder with PDFs")
        if directory:
            added_files = 0
            for root_dir, _, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith(".pdf"):
                        file_path = os.path.join(root_dir, file)
                        if not any(item["path"] == file_path for item in self.pdf_queue):
                            self.pdf_queue.append({"status": "Pending", "path": file_path, "filename": file})
                            added_files += 1
            if added_files > 0:
                self.update_pdf_list()
                self.log(f"Added {added_files} new PDF(s) from {directory}")
            else:
                self.log(f"No new PDF files found in {directory}")

    def select_destination(self):
        directory = filedialog.askdirectory(title="Select Destination Folder")
        if directory:
            self.destination_folder = directory
            self.dest_entry.delete(0, tk.END)
            self.dest_entry.insert(0, self.destination_folder)
            self.log(f"Destination folder set to: {self.destination_folder}")

    def update_pdf_list(self):
        self.pdf_tree.delete(*self.pdf_tree.get_children())
        for item in self.pdf_queue:
            self.pdf_tree.insert("", "end", values=(item["status"], os.path.dirname(item["path"]), item["filename"]))

    def move_item(self, direction):
        selected = self.pdf_tree.focus()
        if not selected:
            self.log("No item selected to move.")
            return
        index = self.pdf_tree.index(selected)
        new_index = index + direction
        if 0 <= new_index < len(self.pdf_queue):
            self.pdf_queue.insert(new_index, self.pdf_queue.pop(index))
            self.update_pdf_list()
            self.pdf_tree.selection_set(self.pdf_tree.get_children()[new_index])
            self.pdf_tree.focus(self.pdf_tree.get_children()[new_index])
            
    def delete_selected_pdfs(self):
        selected_items = self.pdf_tree.selection()
        if not selected_items:
            self.log("No files selected to delete from the list.")
            return
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to remove the selected files from the list?"):
            indices_to_delete = sorted([self.pdf_tree.index(i) for i in selected_items], reverse=True)
            for index in indices_to_delete:
                del self.pdf_queue[index]
            self.update_pdf_list()
            self.log(f"Removed {len(selected_items)} file(s) from the list.")

    def start_conversion(self):
        if not self.tts_engine or not self.tts_engine.model:
            messagebox.showwarning("Model Not Loaded", "Please load a TTS model before starting.")
            return
        
        model_key = self.selected_tts_model.get()
        if "VCTK" in model_key and not self.selected_voice.get():
            messagebox.showwarning("Voice Not Selected", "Please select a voice from the dropdown.")
            return
        if "XTTS" in model_key and not self.speaker_wav_path.get():
            messagebox.showwarning("Voice File Not Selected", "Please select a .wav voice file.")
            return
            
        if self.is_running:
            return
        
        self.is_running = True
        self.is_paused = False
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal", text="Pause")
        self.stop_button.config(state="normal")
        
        self.conversion_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.conversion_thread.start()
        self.log("Conversion process started.")

    def stop_conversion(self):
        if not self.is_running:
            return
        self.is_running = False
        self.is_paused = False
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled", text="Pause")
        self.stop_button.config(state="disabled")
        self.log("Conversion process stopped by user.")

    def pause_resume_conversion(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_button.config(text="Resume")
            self.log("Conversion paused.")
        else:
            self.pause_button.config(text="Pause")
            self.log("Conversion resumed.")

    def process_queue(self):
        speaker_id = None
        speaker_wav = self.speaker_wav_path.get()
        
        if self.tts_engine.model.is_multi_speaker:
            selected_speaker_formatted = self.selected_voice.get()
            speaker_id_match = re.search(r'\(p\d+\)', selected_speaker_formatted)
            if speaker_id_match and hasattr(self.tts_engine.model, 'speakers'):
                speaker_id = speaker_id_match.group(0).strip('()')
            elif hasattr(self.tts_engine.model, 'speakers'):
                speaker_id = self.tts_engine.model.speakers[0]

        for i in range(len(self.pdf_queue) - 1, -1, -1):
            if not self.is_running: break
            while self.is_paused:
                if not self.is_running: break
                time.sleep(1)

            item = self.pdf_queue[i]
            if item["status"] == "Complete": continue

            try:
                self.log(f"Processing: {item['filename']}")
                item["status"] = "Processing"
                self.root.after(0, self.update_pdf_list)

                self.log(f"Extracting text from {item['filename']}...")
                doc = fitz.open(item["path"])
                text = "".join(page.get_text() for page in doc)
                doc.close()
                self.log("Text extraction complete.")
                
                folder_name = os.path.basename(os.path.dirname(item['path']))
                safe_folder_name = "".join(c for c in folder_name if c.isalnum() or c in (' ', '_')).rstrip()
                
                base_filename = f"{safe_folder_name}_{os.path.splitext(item['filename'])[0]}"
                temp_output_path = os.path.join(self.destination_folder, f"{base_filename}_temp.mp3")
                final_output_path = os.path.join(self.destination_folder, f"{base_filename}.mp3")
                
                self.tts_engine.tts(text, temp_output_path, speaker_id=speaker_id, speaker_wav_path=speaker_wav)
                
                if self.optimize_mp3.get() and shutil.which("ffmpeg"):
                    self.log("Optimizing MP3 for fast opening with FFmpeg...")
                    command = [
                        'ffmpeg',
                        '-i', temp_output_path,
                        '-b:a', '192k',
                        '-map_metadata', '-1',
                        '-y',
                        final_output_path
                    ]
                    subprocess.run(command, check=True, capture_output=True)
                    os.remove(temp_output_path)
                    self.log("Optimization complete.")
                else:
                    os.rename(temp_output_path, final_output_path)

                item["status"] = "Complete"
                self.log(f"Successfully converted {item['filename']}")
            except Exception as e:
                item["status"] = "Error"
                self.log(f"ERROR processing {item['filename']}: {e}")
                if 'temp_output_path' in locals() and os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
            self.root.after(0, self.update_pdf_list)

        if self.is_running:
            self.log("All tasks completed.")
            self.root.after(0, self.stop_conversion)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    self.pdf_queue = settings.get("pdf_queue", [])
                    self.destination_folder = settings.get("destination_folder", self.destination_folder)
                    self.selected_voice.set(settings.get("selected_voice", ""))
                    self.speaker_wav_path.set(settings.get("speaker_wav_path", ""))
                    self.selected_tts_model.set(settings.get("selected_tts_model", list(self.available_tts_models.keys())[0]))
                    self.optimize_mp3.set(settings.get("optimize_mp3", True))
            except json.JSONDecodeError:
                self.log("Could not read settings.json, it might be corrupted. Starting fresh.")
                self.pdf_queue = []

    def save_settings(self):
        settings = {
            "pdf_queue": self.pdf_queue,
            "destination_folder": self.destination_folder,
            "selected_voice": self.selected_voice.get(),
            "speaker_wav_path": self.speaker_wav_path.get(),
            "selected_tts_model": self.selected_tts_model.get(),
            "optimize_mp3": self.optimize_mp3.get()
        }
        with open(self.settings_file, 'w') as f:
            json.dump(settings, f, indent=4)

    def on_closing(self):
        if self.is_running:
            if messagebox.askyesno("Confirm Quit", "Conversion is in progress. Are you sure you want to stop and quit?"):
                self.stop_conversion()
                self.save_settings()
                self.root.destroy()
        else:
            self.save_settings()
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFConverterApp(root)
    root.mainloop()
