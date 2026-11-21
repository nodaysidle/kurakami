#!/bin/bash
# Optional: speech recognition for "Time with speech recognition" (Find lyrics, L).
# Puts faster-whisper in its own venv (~500 MB) and downloads the multilingual "small" model (~470 MB) once.
# Everything runs on this machine. Remove with: rm -rf ~/.local/share/kuraoke-kami/whisper
set -e
venv="${XDG_DATA_HOME:-$HOME/.local/share}/kuraoke-kami/whisper"
python3 -m venv "$venv"
"$venv/bin/pip" install -q --upgrade pip
"$venv/bin/pip" install -q faster-whisper
echo "Downloading the speech model (once)..."
"$venv/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"
echo "Speech recognition ready: $venv"
echo "In Kuraoke Kami: L on a song -> Time with speech recognition."
