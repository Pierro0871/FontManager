@echo off
cd /d "%~dp0"
python -c "import PIL, rarfile, fontTools, tkinterdnd2" 2>nul || python -m pip install --user pillow rarfile fonttools tkinterdnd2
start "" pythonw polices.py %*
