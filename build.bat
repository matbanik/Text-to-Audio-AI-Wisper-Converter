@echo OFF
echo ######################################
echo # Setting up build environment...    #
echo ######################################

REM --- Environment Setup Step ---
echo.
echo [SETUP] Checking for virtual environment...
IF NOT EXIST venv (
    echo [SETUP] Virtual environment not found. Creating using Python 3.10...
    d:\Python310\python.exe -m venv venv
    IF %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. Make sure d:\Python310\python.exe exists.
        pause
        exit /b
    )
    echo [SUCCESS] Virtual environment created.
) ELSE (
    echo [INFO] Virtual environment 'venv' already exists. Skipping creation.
)

echo.
echo [SETUP] Activating virtual environment...
CALL venv\Scripts\activate
echo.

REM --- Installation Step 1: PyTorch libraries ---
echo [SETUP] Installing PyTorch, Torchvision, and Torchaudio for CUDA...
pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu128
IF %errorlevel% neq 0 (
    echo [ERROR] Failed to install PyTorch libraries. Please check your internet connection and the command.
    pause
    exit /b
)

REM --- Installation Step 2: Main application libraries ---
echo.
echo [SETUP] Installing main application dependencies...
pip install phonemizer PyMuPDF pyinstaller frontend fitz transformers==4.41.2
IF %errorlevel% neq 0 (
    echo [ERROR] Failed to install main dependencies.
    pause
    exit /b
)

REM --- Installation Step 3: Compatibility fixes ---
echo.
echo [SETUP] Uninstalling conflicting 'pathlib' package for compatibility...
pip uninstall -y pathlib
echo [SUCCESS] Environment setup is complete.
echo.
REM ---------------------------------

echo ######################################
echo # Building kokoro.exe executable...  #
echo ######################################

REM --- Validation Step ---
echo.
echo [VALIDATION] Checking if TTS library is accessible...
python -c "import TTS.api"
if %errorlevel% neq 0 (
    echo [ERROR] TTS library not found in the current environment.
    echo Please ensure you have activated the correct virtual environment and run 'pip install TTS'.
    pause
    exit /b
)
echo [SUCCESS] TTS library found.
echo Proceeding with build...
echo.
REM ---------------------

REM This command now builds the application using the pyinstaller.exe
REM located directly inside the virtual environment's Scripts folder.
REM This ensures the correct Python version (3.10) is used for the build.
venv\Scripts\pyinstaller.exe kokoro.spec

echo.
echo ##########################################
echo # Build complete!
echo #
echo # Look in the 'dist' folder for kokoro.exe
echo ##########################################
pause
