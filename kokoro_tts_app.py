"""
Kokoro-82M Text-to-Speech Standalone Application
A simple UI for converting text to speech using Kokoro-82M model.
Supports NVIDIA RTX 5080 and other CUDA-compatible GPUs.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import shutil
from pathlib import Path
import numpy as np
import soundfile as sf
import subprocess
import traceback
import re
import logging
import json

# Early multiprocessing guard for Windows
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if hasattr(multiprocessing, 'current_process'):
        try:
            current = multiprocessing.current_process()
            if current.name != 'MainProcess':
                sys.exit(0)
        except:
            pass

# Set environment variables for Windows
if sys.platform.startswith('win'):
    os.environ['PYTHONW'] = '1'
    os.environ['_MP_FORK_EXEC_'] = '1'

# Fix for PyInstaller windowed mode: sys.stderr may be None
# This must be done BEFORE importing kokoro (which uses loguru)
if getattr(sys, 'frozen', False):
    # Running as PyInstaller executable
    if sys.stderr is None:
        import io
        sys.stderr = io.StringIO()
    if sys.stdout is None:
        import io
        sys.stdout = io.StringIO()
    
    # Fix for spaCy model loading in PyInstaller
    # Add the _internal directory to sys.path so spaCy can find the model
    if hasattr(sys, '_MEIPASS'):
        sys.path.insert(0, sys._MEIPASS)
        # Also try to import en_core_web_sm if it's bundled
        try:
            import en_core_web_sm
            # Ensure spaCy can find the model by adding it to sys.path
            en_core_path = os.path.dirname(en_core_web_sm.__file__)
            if en_core_path not in sys.path:
                sys.path.insert(0, en_core_path)
        except ImportError:
            pass
        
        # Monkey-patch spaCy's load function to look in PyInstaller bundle
        # This must be done BEFORE kokoro imports spacy
        # Import spacy early and patch it
        import spacy
        import spacy.util
        original_load = spacy.load
        original_load_model = spacy.util.load_model
        
        def patched_load(name, **kwargs):
            # First try the original load
            try:
                return original_load(name, **kwargs)
            except OSError as e:
                # If it fails, try to find the model in the bundle
                if hasattr(sys, '_MEIPASS'):
                    # Try direct path
                    model_path = os.path.join(sys._MEIPASS, name)
                    if os.path.exists(model_path):
                        return original_load(model_path, **kwargs)
                    # Try as a package (en_core_web_sm)
                    try:
                        model_module = __import__(name)
                        model_dir = os.path.dirname(model_module.__file__)
                        if os.path.exists(model_dir):
                            return original_load(model_dir, **kwargs)
                    except ImportError:
                        pass
                # Re-raise the original error
                raise
        
        def patched_load_model(name, **kwargs):
            # First try the original load_model
            try:
                return original_load_model(name, **kwargs)
            except OSError as e:
                # If it fails, try to find the model in the bundle
                if hasattr(sys, '_MEIPASS'):
                    # Try direct path
                    model_path = os.path.join(sys._MEIPASS, name)
                    if os.path.exists(model_path):
                        return original_load_model(model_path, **kwargs)
                    # Try as a package (en_core_web_sm)
                    try:
                        model_module = __import__(name)
                        model_dir = os.path.dirname(model_module.__file__)
                        if os.path.exists(model_dir):
                            return original_load_model(model_dir, **kwargs)
                    except ImportError:
                        pass
                # Re-raise the original error
                raise
        
        spacy.load = patched_load
        spacy.util.load_model = patched_load_model

# Import PyTorch first (required for device detection)
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    try:
        print("Warning: PyTorch not available")
    except:
        pass

# Import Kokoro and dependencies
try:
    if TORCH_AVAILABLE:
        from kokoro import KPipeline
        KOKORO_AVAILABLE = True
    else:
        KOKORO_AVAILABLE = False
        KPipeline = None
except ImportError as e:
    KOKORO_AVAILABLE = False
    KPipeline = None
    try:
        print(f"Error: Kokoro not available: {e}")
    except:
        pass

# Kokoro voice options (all available voices)
KOKORO_VOICES = [
    "af_bella", "af_sarah", "af_sky", "af_heart", "af_nicole",
    "af_alloy", "af_aoede", "af_river", "af_nova", "af_jessica", "af_kore",
    "am_adam", "am_michael", "am_eric", "am_onyx", "am_liam",
    "am_echo", "am_fenrir", "am_puck", "am_santa"
]

# Log levels for filtering
LOG_LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class TextLineNumbers(tk.Canvas):
    """Canvas widget that displays line numbers for a text widget."""
    def __init__(self, parent, text_widget):
        super().__init__(parent, width=50, bg="#f0f0f0", highlightthickness=0)
        self.text_widget = text_widget
        self.text_widget.bind("<KeyPress>", self.on_key_press)
        self.text_widget.bind("<Button-1>", self.on_key_press)
        self.text_widget.bind("<MouseWheel>", self.on_key_press)
        self.update_line_numbers()
    
    def on_key_press(self, event=None):
        self.after_idle(self.update_line_numbers)
    
    def update_line_numbers(self):
        """Update the line numbers display."""
        self.delete("all")
        i = self.text_widget.index("@0,0")
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None:
                break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.create_text(2, y, anchor="nw", text=linenum, fill="#666", font=("Courier", 10))
            i = self.text_widget.index(f"{i}+1line")
            if i == self.text_widget.index("end"):
                break


class TextWithLineNumbers(tk.Frame):
    """Text widget with line numbers on the left."""
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent)
        self.text = tk.Text(self, *args, **kwargs)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.vsb.set)
        self.linenumbers = TextLineNumbers(self, self.text)
        
        self.linenumbers.pack(side="left", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
    
    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        result = self.text.delete(*args, **kwargs)
        self.linenumbers.update_line_numbers()
        return result
    
    def insert(self, *args, **kwargs):
        result = self.text.insert(*args, **kwargs)
        self.linenumbers.update_line_numbers()
        return result
    
    def bind(self, *args, **kwargs):
        self.text.bind(*args, **kwargs)

class KokoroTTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kokoro-82M Text-to-Speech")
        self.root.geometry("900x800")
        
        # State
        self.pipeline = None
        if TORCH_AVAILABLE and torch.cuda.is_available():
            self.device = "cuda"
        elif TORCH_AVAILABLE and torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        
        self.is_processing = False
        self.output_format = tk.StringVar(value="wav")
        self.selected_voice = tk.StringVar(value=KOKORO_VOICES[0])
        self.speed = tk.DoubleVar(value=1.0)
        
        # Console visibility and filtering
        self.console_visible = tk.BooleanVar(value=False)  # Hidden by default
        self.log_level_filter = tk.StringVar(value="INFO")
        self.log_messages = []  # Store all log messages for filtering
        
        # Settings file path
        self.settings_file = Path(__file__).parent / "kokoro-settings.json"
        self.save_timer = None  # For debounced saving
        self.loading_settings = False  # Flag to prevent saves during loading
        
        # Check FFmpeg before setting up UI
        self.has_ffmpeg = shutil.which("ffmpeg") is not None
        
        # Setup UI first (so log_text exists)
        self.setup_ui()
        
        # Load saved settings
        self.load_settings()
        
        # Check CUDA availability (after UI is set up)
        self.check_cuda()
        
        # Log FFmpeg status
        if not self.has_ffmpeg:
            self.output_format.set("wav")  # Force WAV if no FFmpeg
            self.log("FFmpeg not found - MP3 output disabled. WAV format will be used.", level="WARNING")
    
    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = tk.Label(tooltip, text=text, background="#ffffe0", 
                           relief="solid", borderwidth=1, padx=5, pady=2,
                           font=("Arial", 9))
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def check_cuda(self):
        """Check CUDA availability and log GPU info."""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            self.log(f"CUDA available - GPU: {gpu_name}", level="INFO")
            self.log(f"CUDA version: {torch.version.cuda}", level="INFO")
        else:
            self.log("CUDA not available - using CPU (slower)", level="WARNING")
    
    def load_settings(self):
        """Load settings from kokoro-settings.json."""
        if not self.settings_file.exists():
            self.loading_settings = False
            return
        
        self.loading_settings = True
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            # Load voice
            if 'voice' in settings and settings['voice'] in KOKORO_VOICES:
                self.selected_voice.set(settings['voice'])
            
            # Load speed
            if 'speed' in settings:
                try:
                    speed_val = float(settings['speed'])
                    if 0.5 <= speed_val <= 2.0:
                        self.speed.set(speed_val)
                except (ValueError, TypeError):
                    pass
            
            # Load output format
            if 'output_format' in settings and settings['output_format'] in ['wav', 'mp3']:
                if settings['output_format'] == 'mp3' and not self.has_ffmpeg:
                    self.output_format.set('wav')
                else:
                    self.output_format.set(settings['output_format'])
            
            # Load output path
            if 'output_path' in settings:
                path = Path(settings['output_path'])
                if path.exists() or path.parent.exists():
                    self.output_path.set(str(path))
            
            # Load text input
            if 'text_input' in settings:
                self.text_input.delete(1.0, tk.END)
                self.text_input.insert(1.0, settings['text_input'])
                self.update_text_stats()
            
            # Load console visibility
            if 'console_visible' in settings:
                self.console_visible.set(bool(settings['console_visible']))
                self.toggle_console()
            
            # Load log filter
            if 'log_level_filter' in settings and settings['log_level_filter'] in LOG_LEVELS:
                self.log_level_filter.set(settings['log_level_filter'])
                self.filter_logs()
            
            self.log("Settings loaded from kokoro-settings.json", level="INFO")
        except Exception as e:
            self.log(f"Error loading settings: {e}", level="WARNING")
        finally:
            self.loading_settings = False
    
    def save_settings(self):
        """Save current settings to kokoro-settings.json."""
        try:
            settings = {
                'voice': self.selected_voice.get(),
                'speed': self.speed.get(),
                'output_format': self.output_format.get(),
                'output_path': self.output_path.get(),
                'text_input': self.text_input.text.get(1.0, tk.END).strip(),
                'console_visible': self.console_visible.get(),
                'log_level_filter': self.log_level_filter.get()
            }
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Error saving settings: {e}", level="ERROR")
    
    def debounced_save(self):
        """Schedule a save after 400ms delay (debounced)."""
        # Don't save if we're currently loading settings
        if self.loading_settings:
            return
        
        # Cancel existing timer if any
        if self.save_timer is not None:
            self.root.after_cancel(self.save_timer)
        
        # Schedule new save
        self.save_timer = self.root.after(400, self.save_settings)
    
    def calculate_text_stats(self):
        """Calculate text statistics: bytes, words, sentences, lines, tokens."""
        text = self.text_input.text.get(1.0, tk.END).strip()
        
        # Bytes
        bytes_count = len(text.encode('utf-8'))
        
        # Words (split by whitespace)
        words = text.split()
        words_count = len(words)
        
        # Sentences (split by . ! ?)
        sentences = re.split(r'[.!?]+', text)
        sentences_count = len([s for s in sentences if s.strip()])
        
        # Lines
        lines_count = len(text.split('\n'))
        
        # Tokens (simple approximation: words + punctuation)
        tokens = re.findall(r'\b\w+\b|[^\w\s]', text)
        tokens_count = len(tokens)
        
        return bytes_count, words_count, sentences_count, lines_count, tokens_count
    
    def update_text_stats(self):
        """Update the text statistics display."""
        bytes_count, words_count, sentences_count, lines_count, tokens_count = self.calculate_text_stats()
        stats_text = f"Bytes: {bytes_count} | Words: {words_count} | Sentence: {sentences_count} | Line: {lines_count} | Tokens: {tokens_count}"
        self.stats_label.config(text=stats_text)
    
    def setup_ui(self):
        """Setup the user interface."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # ========== CONFIGURATION SECTION ==========
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="5")
        config_frame.pack(fill="x", pady=(0, 10))
        
        # Row 1: Device | Voice | Speed
        row1 = ttk.Frame(config_frame)
        row1.pack(fill="x", pady=(0, 5))
        
        # Device label
        ttk.Label(row1, text="Device:").pack(side="left", padx=5)
        self.device_label = ttk.Label(row1, text=self.device.upper(), font=("Arial", 9, "bold"))
        self.device_label.pack(side="left", padx=(0, 15))
        
        # Voice dropdown
        ttk.Label(row1, text="Voice:").pack(side="left", padx=5)
        voice_combo = ttk.Combobox(row1, textvariable=self.selected_voice, 
                                   values=KOKORO_VOICES, state="readonly", width=20)
        voice_combo.pack(side="left", padx=5)
        voice_combo.bind("<<ComboboxSelected>>", lambda e: self.debounced_save())
        
        # Speed slider
        ttk.Label(row1, text="Speed:").pack(side="left", padx=(15, 5))
        speed_scale = ttk.Scale(row1, from_=0.5, to=2.0, variable=self.speed, 
                                orient="horizontal", length=150)
        speed_scale.pack(side="left", padx=5)
        self.speed_label = ttk.Label(row1, text="1.0x")
        self.speed_label.pack(side="left", padx=5)
        speed_scale.configure(command=lambda v: [self.speed_label.config(text=f"{float(v):.1f}x"), self.debounced_save()])
        
        # Row 2: Output format | Output Save to
        row2 = ttk.Frame(config_frame)
        row2.pack(fill="x", pady=(0, 5))
        
        # Output format radiobuttons
        ttk.Label(row2, text="Output Format:").pack(side="left", padx=5)
        ttk.Radiobutton(row2, text="WAV", variable=self.output_format, 
                       value="wav").pack(side="left", padx=5)
        mp3_radio = ttk.Radiobutton(row2, text="MP3", variable=self.output_format, 
                                   value="mp3")
        mp3_radio.pack(side="left", padx=5)
        if not self.has_ffmpeg:
            mp3_radio.config(state="disabled")
        self.output_format.trace('w', lambda *args: self.debounced_save())
        
        # Output path
        ttk.Label(row2, text="Output Save to:").pack(side="left", padx=(20, 5))
        self.output_path = tk.StringVar(value=str(Path.home() / "Downloads"))
        output_entry = ttk.Entry(row2, textvariable=self.output_path, width=35)
        output_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.output_path.trace('w', lambda *args: self.debounced_save())
        ttk.Button(row2, text="Browse", command=self.select_output_dir).pack(side="left", padx=5)
        ttk.Button(row2, text="Open Folder", command=self.open_output_folder).pack(side="left", padx=5)
        
        # Row 3: Play, Stop, and file control buttons
        row3 = ttk.Frame(config_frame)
        row3.pack(fill="x")
        
        # Play button (icon) with tooltip
        play_icon = "▶"  # Unicode play symbol
        self.generate_button = tk.Button(row3, text=play_icon, font=("Arial", 16), 
                                         command=self.start_generation, 
                                         width=3, height=1, relief="raised")
        self.generate_button.pack(side="left", padx=5)
        self.create_tooltip(self.generate_button, "Generate speech from the text input")
        
        # Stop button (icon) with tooltip
        stop_icon = "■"  # Unicode stop symbol
        self.stop_button = tk.Button(row3, text=stop_icon, font=("Arial", 16), 
                                     command=self.stop_generation, 
                                     width=3, height=1, relief="raised", state="disabled")
        self.stop_button.pack(side="left", padx=5)
        self.create_tooltip(self.stop_button, "Stop the current speech generation")
        
        # Load from File button
        ttk.Button(row3, text="Load from File", 
                  command=self.load_text_file).pack(side="left", padx=5)
        
        # Clear button
        ttk.Button(row3, text="Clear", 
                  command=lambda: [self.text_input.delete(1.0, tk.END), self.update_text_stats(), self.debounced_save()]).pack(side="left", padx=5)
        
        # ========== INPUT TEXT-TO-SPEECH SECTION ==========
        self.text_frame = ttk.LabelFrame(main_frame, text="Input Text-to-Speech", padding="5")
        self.text_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Text area with line numbers
        text_container = ttk.Frame(self.text_frame)
        text_container.pack(fill="both", expand=True)
        
        self.text_input = TextWithLineNumbers(text_container, height=12, wrap="word")
        self.text_input.pack(fill="both", expand=True)
        
        # Bind text changes to update statistics and save settings
        self.text_input.text.bind("<KeyRelease>", lambda e: [self.update_text_stats(), self.debounced_save()])
        self.text_input.text.bind("<Button-1>", lambda e: self.update_text_stats())
        
        # Text statistics bar
        stats_frame = ttk.Frame(self.text_frame)
        stats_frame.pack(fill="x", pady=(5, 0))
        self.stats_label = ttk.Label(stats_frame, text="Bytes: 0 | Words: 0 | Sentence: 0 | Line: 0 | Tokens: 0")
        self.stats_label.pack(side="left", padx=5)
        
        # ========== CONSOLE OUTPUT SECTION ==========
        self.log_frame = ttk.LabelFrame(main_frame, text="Console Output", padding="5")
        self.log_frame.pack(fill="both", expand=True)
        
        # Console controls
        console_controls = ttk.Frame(self.log_frame)
        console_controls.pack(fill="x", pady=(0, 5))
        
        ttk.Label(console_controls, text="Console Output:").pack(side="left", padx=5)
        
        # Show Console checkbox
        show_console_check = ttk.Checkbutton(console_controls, text="Show Console", 
                                            variable=self.console_visible,
                                            command=lambda: [self.toggle_console(), self.debounced_save()])
        show_console_check.pack(side="left", padx=(10, 5))
        
        # Filter dropdown
        ttk.Label(console_controls, text="Filter:").pack(side="left", padx=(10, 5))
        filter_combo = ttk.Combobox(console_controls, textvariable=self.log_level_filter,
                                    values=LOG_LEVELS, state="readonly", width=12)
        filter_combo.pack(side="left", padx=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: [self.filter_logs(), self.debounced_save()])
        
        # Console log area (initially not packed - will be packed by toggle_console)
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=8, state="disabled", 
                                                   bg="black", fg="#ffff00", wrap="word", 
                                                   font=("Consolas", 9))
        # Don't pack initially - toggle_console will handle it
        
        # Initial log
        self.log("Kokoro-82M Text-to-Speech Application", level="INFO")
        self.log(f"Device: {self.device.upper()}", level="INFO")
        if self.device == "cuda" and TORCH_AVAILABLE:
            self.log(f"GPU: {torch.cuda.get_device_name(0)}", level="INFO")
        self.log("Ready. Enter text and click Play to generate speech.", level="INFO")
        
        # Initialize text statistics
        self.update_text_stats()
        
        # Set initial console state (hidden by default - minimizes console, maximizes text area)
        self.toggle_console()
    
    def log(self, message, level="INFO"):
        """Add message to log with level filtering."""
        # Store message with level
        log_entry = {"message": message, "level": level}
        self.log_messages.append(log_entry)
        
        # Apply filter
        self.filter_logs()
        
        # Print to console with safe encoding
        try:
            print(f"[{level}] {message}")
        except UnicodeEncodeError:
            safe_message = f"[{level}] {message}".encode('ascii', 'replace').decode('ascii')
            print(safe_message)
    
    def toggle_console(self):
        """Toggle console visibility and adjust text area size."""
        if self.console_visible.get():
            # Show console - minimize log_frame but keep controls visible
            self.log_text.pack(fill="both", expand=True)
            self.log_frame.pack(fill="both", expand=True)
            # Reduce text_frame expansion
            self.text_frame.pack(fill="both", expand=True, pady=(0, 10))
        else:
            # Hide console - minimize log_frame to just controls
            self.log_text.pack_forget()
            # Minimize log_frame to just show controls
            self.log_frame.pack(fill="x", expand=False)
            # Maximize text_frame expansion
            self.text_frame.pack(fill="both", expand=True, pady=(0, 10))
    
    def filter_logs(self):
        """Filter and display logs based on selected level."""
        selected_level = self.log_level_filter.get()
        
        # Map log levels to numeric values for comparison
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        
        # Filter and display messages
        for entry in self.log_messages:
            entry_level = entry["level"]
            
            if selected_level == "ALL":
                should_show = True
            elif selected_level in level_order and entry_level in level_order:
                # Show messages at or above the selected level
                should_show = level_order[entry_level] >= level_order[selected_level]
            else:
                should_show = True
            
            if should_show:
                # Color code by level
                color = "#ffff00"  # Default yellow
                tag_name = f"level_{entry_level}"
                if entry_level == "DEBUG":
                    color = "#888888"  # Gray
                elif entry_level == "INFO":
                    color = "#00ff00"  # Green
                elif entry_level == "WARNING":
                    color = "#ffaa00"  # Orange
                elif entry_level == "ERROR":
                    color = "#ff0000"  # Red
                elif entry_level == "CRITICAL":
                    color = "#ff00ff"  # Magenta
                
                # Insert message and tag it
                start_pos = self.log_text.index(tk.END)
                self.log_text.insert(tk.END, f"[{entry_level}] {entry['message']}\n")
                end_pos = self.log_text.index(tk.END + "-1c")
                
                # Apply color tag
                self.log_text.tag_add(tag_name, start_pos, end_pos)
                self.log_text.tag_config(tag_name, foreground=color)
        
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
    
    def load_text_file(self):
        """Load text from a file."""
        filepath = filedialog.askopenfilename(
            title="Select Text File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.text_input.delete(1.0, tk.END)
                self.text_input.insert(1.0, content)
                self.update_text_stats()
                self.debounced_save()
                self.log(f"Loaded text from: {os.path.basename(filepath)}", level="INFO")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")
                self.log(f"Error loading file: {e}", level="ERROR")
    
    def select_output_dir(self):
        """Select output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_path.set(directory)
            self.log(f"Output directory: {directory}", level="INFO")
            self.debounced_save()
    
    def open_output_folder(self):
        """Open the output folder in the system file manager."""
        folder_path = Path(self.output_path.get())
        if not folder_path.exists():
            try:
                folder_path.mkdir(parents=True, exist_ok=True)
                self.log(f"Created output directory: {folder_path}", level="INFO")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create directory: {e}")
                return
        
        try:
            if sys.platform.startswith('win'):
                os.startfile(str(folder_path))
            elif sys.platform.startswith('darwin'):
                subprocess.run(['open', str(folder_path)])
            else:
                subprocess.run(['xdg-open', str(folder_path)])
            self.log(f"Opened folder: {folder_path}", level="INFO")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder: {e}")
            self.log(f"Error opening folder: {e}", level="ERROR")
    
    def show_success_dialog(self, output_file, output_dir, duration):
        """Show success dialog with Open and To Folder buttons."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Success")
        dialog.geometry("450x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Main frame
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill="both", expand=True)
        
        # Success icon and message
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill="x", pady=(0, 15))
        
        # Icon (using a simple label with text)
        icon_label = ttk.Label(info_frame, text="✓", font=("Arial", 24), foreground="green")
        icon_label.pack(side="left", padx=(0, 15))
        
        # Message
        msg_frame = ttk.Frame(info_frame)
        msg_frame.pack(side="left", fill="both", expand=True)
        
        ttk.Label(msg_frame, text="Audio generated successfully!", 
                 font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(msg_frame, text=f"File: {output_file.name}").pack(anchor="w", pady=(5, 0))
        ttk.Label(msg_frame, text=f"Location: {output_dir}").pack(anchor="w")
        ttk.Label(msg_frame, text=f"Duration: {duration:.2f} seconds").pack(anchor="w")
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        def open_file():
            """Open the file with default system player."""
            try:
                if sys.platform.startswith('win'):
                    os.startfile(str(output_file))
                elif sys.platform.startswith('darwin'):
                    subprocess.run(['open', str(output_file)])
                else:
                    subprocess.run(['xdg-open', str(output_file)])
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {e}")
        
        def open_folder():
            """Open the folder containing the file."""
            try:
                if sys.platform.startswith('win'):
                    os.startfile(str(output_dir))
                elif sys.platform.startswith('darwin'):
                    subprocess.run(['open', str(output_dir)])
                else:
                    subprocess.run(['xdg-open', str(output_dir)])
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder: {e}")
        
        # Buttons
        ttk.Button(button_frame, text="Open", command=open_file, width=12).pack(side="left", padx=5)
        ttk.Button(button_frame, text="To Folder", command=open_folder, width=12).pack(side="left", padx=5)
        ttk.Button(button_frame, text="OK", command=dialog.destroy, width=12).pack(side="right", padx=5)
    
    def start_generation(self):
        """Start text-to-speech generation in a separate thread."""
        if self.is_processing:
            messagebox.showwarning("Warning", "Generation is already in progress.")
            return
        
        # Get text
        text = self.text_input.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some text to convert.")
            return
        
        # Check Kokoro availability
        if not KOKORO_AVAILABLE:
            messagebox.showerror("Error", "Kokoro package not available. Please install it.")
            return
        
        # Disable controls
        self.is_processing = True
        self.generate_button.config(state="disabled")
        self.stop_button.config(state="normal")
        
        # Start generation in thread
        thread = threading.Thread(target=self.generate_speech, args=(text,), daemon=True)
        thread.start()
    
    def stop_generation(self):
        """Stop generation (placeholder - would need pipeline cancellation)."""
        self.is_processing = False
        self.log("Stop requested (generation will finish current segment)...", level="WARNING")
    
    def generate_speech(self, text):
        """Generate speech from text."""
        try:
            self.log("Initializing Kokoro pipeline...", level="INFO")
            
            # Get parameters
            voice = self.selected_voice.get()
            speed = self.speed.get()
            lang_code = voice[0]  # Extract language code from voice (a=English)
            
            # Initialize pipeline if needed
            if self.pipeline is None:
                self.log(f"Loading Kokoro-82M model (this may take a moment)...", level="INFO")
                self.pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", 
                                         device=self.device)
                self.log("Pipeline initialized successfully", level="INFO")
            
            # Process text
            self.log(f"Processing text with voice '{voice}' at speed {speed:.1f}x...", level="INFO")
            audio_segments = []
            segment_count = 0
            
            for gs, ps, audio in self.pipeline(text, voice=voice, speed=speed, 
                                              split_pattern=r'\n\n\n'):
                if not self.is_processing:
                    break
                audio_segments.append(audio)
                segment_count += 1
                if segment_count % 10 == 0:
                    self.log(f"Processed {segment_count} segments...", level="DEBUG")
            
            if not audio_segments:
                raise RuntimeError("No audio generated")
            
            # Concatenate audio
            self.log("Concatenating audio segments...", level="INFO")
            final_audio = np.concatenate(audio_segments)
            self.log(f"Generated {len(final_audio)} samples at 24kHz", level="INFO")
            
            # Save audio
            output_format = self.output_format.get()
            output_dir = Path(self.output_path.get())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get voice name for filename
            voice = self.selected_voice.get()
            
            if output_format == "mp3" and self.has_ffmpeg:
                # Save as WAV first, then convert to MP3
                temp_wav = output_dir / "temp_kokoro_output.wav"
                sf.write(str(temp_wav), final_audio, 24000)
                
                output_file = output_dir / f"kokoro_{voice}_{segment_count}.mp3"
                self.log(f"Converting to MP3...", level="INFO")
                subprocess.run([
                    'ffmpeg', '-i', str(temp_wav), '-acodec', 'libmp3lame',
                    '-ab', '192k', '-y', str(output_file)
                ], check=True, capture_output=True)
                os.remove(temp_wav)
            else:
                # Save as WAV
                output_file = output_dir / f"kokoro_{voice}_{segment_count}.wav"
                sf.write(str(output_file), final_audio, 24000)
            
            # Success
            duration = len(final_audio) / 24000
            file_size = output_file.stat().st_size / 1024  # KB
            self.log(f"[SUCCESS] Audio saved: {output_file.name}", level="INFO")
            self.log(f"  Duration: {duration:.2f} seconds", level="INFO")
            self.log(f"  File size: {file_size:.2f} KB", level="INFO")
            
            # Show success message with action buttons
            self.root.after(0, lambda: self.show_success_dialog(
                output_file, output_dir, duration
            ))
            
        except Exception as e:
            error_msg = f"Error during generation: {e}"
            self.log(error_msg, level="ERROR")
            self.log(traceback.format_exc(), level="ERROR")
            self.root.after(0, lambda: messagebox.showerror("Error", error_msg))
        finally:
            # Re-enable controls
            self.is_processing = False
            self.root.after(0, lambda: self.generate_button.config(state="normal"))
            self.root.after(0, lambda: self.stop_button.config(state="disabled"))


def main():
    """Main entry point."""
    if not KOKORO_AVAILABLE:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing Dependency",
            "Kokoro package is not installed.\n\n"
            "Please install it with:\n"
            "pip install kokoro numpy soundfile"
        )
        sys.exit(1)
    
    root = tk.Tk()
    app = KokoroTTSApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

