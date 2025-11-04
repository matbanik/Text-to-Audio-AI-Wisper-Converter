# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Kokoro-82M TTS Application

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# Find site-packages
site_packages = next((p for p in sys.path if 'site-packages' in p), None)

# Manually include espeak-ng-data directory if it exists
espeak_data_files = []
if site_packages:
    espeak_loader_path = os.path.join(site_packages, 'espeakng_loader')
    espeak_data_path = os.path.join(espeak_loader_path, 'espeak-ng-data')
    if os.path.exists(espeak_data_path):
        espeak_data_files = [(espeak_data_path, 'espeakng_loader/espeak-ng-data')]

# Manually include spaCy model en_core_web_sm if it exists
# Use Tree to recursively include all files in the model directory
spacy_model_files = []
if site_packages:
    spacy_model_path = os.path.join(site_packages, 'en_core_web_sm')
    if os.path.exists(spacy_model_path):
        # Use Tree to include entire directory recursively
        from PyInstaller.utils.hooks import collect_data_files
        # Try collect_data_files first
        try:
            spacy_model_files = collect_data_files('en_core_web_sm', include_py_files=True)
        except:
            pass
        # If that didn't work or returned empty, use Tree
        if not spacy_model_files:
            try:
                from PyInstaller.building.utils import format_binaries_and_datas
                # Manually create Tree-like structure
                import glob
                model_files = []
                for root, dirs, files in os.walk(spacy_model_path):
                    for file in files:
                        src = os.path.join(root, file)
                        # Get relative path from model directory
                        rel_path = os.path.relpath(src, spacy_model_path)
                        dst = os.path.join('en_core_web_sm', rel_path).replace('\\', '/')
                        model_files.append((src, dst))
                spacy_model_files = model_files
            except Exception as e:
                # Fallback: just include the directory
                spacy_model_files = [(spacy_model_path, 'en_core_web_sm')]

a = Analysis(
    ['kokoro_tts_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('voices', 'voices'),
    ] + collect_data_files('kokoro', include_py_files=True) + collect_data_files('language_tags') + collect_data_files('segments') + collect_data_files('csvw') + collect_data_files('espeakng_loader') + espeak_data_files + spacy_model_files,
    hiddenimports=[
        'kokoro',
        'kokoro.pipeline',
        'numpy',
        'soundfile',
        'spacy',
        'phonemizer',
        'phonemizer.backend',
        'language_tags',
        'language_tags.data',
        'segments',
        'csvw',
        'espeakng_loader',
        'en_core_web_sm',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='kokoro_tts',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='kokoro_tts',
)

