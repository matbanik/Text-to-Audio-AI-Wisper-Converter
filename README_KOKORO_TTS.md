# Kokoro-82M Text-to-Speech Application

A simple, standalone GUI application for converting text to speech using the Kokoro-82M model. **Optimized for NVIDIA RTX 5000 series graphics cards (RTX 5080, RTX 5090, etc.) running on Windows 11** with CUDA acceleration.

## Features

- **Simple UI**: Clean, intuitive interface for text-to-speech conversion
- **Multiple Voices**: 19 different voices (American Female and American Male)
- **Speed Control**: Adjustable speech speed from 0.5x to 2.0x
- **Input Formats**: Direct text input or load from text files (.txt)
- **Output Formats**: WAV (always) and MP3 (if FFmpeg is installed)
- **CUDA Support**: Automatic GPU detection and utilization (optimized for RTX 5000 series)
- **Settings Persistence**: Automatically saves your preferences and text input
- **Standalone**: Can be built as a single executable file

## Requirements

### Python Dependencies
- Python 3.10 or higher
- PyTorch (with CUDA support for RTX 5080)
- Kokoro package
- NumPy
- SoundFile

### Optional
- FFmpeg (for MP3 output support)

## Installation

### Prerequisites

- **Windows 11** (recommended)
- **NVIDIA RTX 5000 series GPU** (RTX 5080, RTX 5090, etc.) with CUDA support
- **Conda** (Miniconda or Anaconda)
- **Python 3.10** or higher

### 1. Create and Activate Conda Environment

Open a terminal (PowerShell or Command Prompt) and run:

```bash
conda create -n kokoro_build python=3.10
conda activate kokoro_build
```

### 2. Install PyTorch with CUDA Support

For NVIDIA RTX 5000 series (CUDA 12.x):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Note**: For RTX 5000 series cards, use CUDA 12.x (cu121) for optimal performance.

For CPU only (not recommended, very slow):
```bash
pip install torch torchvision torchaudio
```

### 3. Install Application Dependencies

```bash
pip install -r requirements_simple.txt
```

This will install:
- `kokoro` - The Kokoro-82M TTS library
- `numpy` - Numerical operations
- `soundfile` - Audio file I/O

## Usage

### Running from Source (Recommended for Development)

#### Option 1: Using run.bat (Easiest)

Simply double-click `run.bat` or run it from the command line:

```bash
run.bat
```

This script automatically:
- Activates the `kokoro_build` conda environment
- Launches the application

#### Option 2: Manual Command Line

1. Activate the conda environment:
   ```bash
   conda activate kokoro_build
   ```

2. Run the application:
   ```bash
   python kokoro_tts_app.py
   ```

### Building Standalone Executable

To build a standalone executable that doesn't require Python or conda:

1. Make sure you're in the conda environment:
   ```bash
   conda activate kokoro_build
   ```

2. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

3. Build using the spec file:
   ```bash
   pyinstaller kokoro_tts.spec
   ```

4. The executable will be in `dist\kokoro_tts\kokoro_tts.exe`

**Note**: The executable will be large (~2-3GB) as it includes all dependencies and models.

## How to Use

1. **Select Voice**: Choose from 19 available voices (af_* = American Female, am_* = American Male)

2. **Adjust Speed**: Use the slider to set speech speed (0.5x to 2.0x)

3. **Enter Text**: 
   - Type text directly in the text area, OR
   - Click "Load from File" to load from a .txt file

4. **Choose Output Format**: 
   - WAV (always available)
   - MP3 (requires FFmpeg)

5. **Select Output Directory**: Choose where to save the audio file

6. **Generate**: Click "Generate Speech" to convert text to speech

## Supported Voices

### American Female (af_*)
- af_bella, af_sarah, af_sky, af_heart, af_nicole
- af_alloy, af_aoede, af_river, af_nova, af_jessica, af_kore

### American Male (am_*)
- am_adam, am_michael, am_eric, am_onyx, am_liam
- am_echo, am_fenrir, am_puck, am_santa

## Technical Details

- **Sample Rate**: 24 kHz
- **Audio Format**: 24-bit WAV (converted to MP3 if FFmpeg available)
- **Device Detection**: Automatically uses CUDA if available, falls back to CPU
- **Processing**: Non-blocking (runs in background thread)
- **Settings**: Automatically saves to `kokoro-settings.json` in the application directory
- **Optimization**: Optimized for NVIDIA RTX 5000 series GPUs with CUDA 12.x

## Troubleshooting

### CUDA Not Detected
- Ensure PyTorch was installed with CUDA 12.x support (`cu121`)
- Check that NVIDIA drivers are up to date (RTX 5000 series requires latest drivers)
- Verify CUDA is available: `python -c "import torch; print(torch.cuda.is_available())"`
- Check GPU detection: `python -c "import torch; print(torch.cuda.get_device_name(0))"`

### MP3 Output Not Available
- Install FFmpeg and ensure it's in your system PATH
- Or use WAV format (always available)
- Download FFmpeg from: https://ffmpeg.org/download.html

### Model Download Issues
- First run will download the Kokoro-82M model (~300MB)
- Ensure you have internet connection and sufficient disk space
- The model is cached locally for future use

### Conda Environment Issues
- Make sure you're using the correct environment name: `kokoro_build`
- If `run.bat` doesn't work, manually activate: `conda activate kokoro_build`
- Verify Python version: `python --version` (should be 3.10+)

## Notes

- The application is designed to be simple and focused
- No PDF support - text input only
- First generation may take longer as the model initializes
- Subsequent generations are faster (model stays in memory)

## License

This application uses the Kokoro-82M model. Please refer to the Kokoro project license for model usage terms.

