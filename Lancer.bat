@echo off
cd /d "%~dp0"
python -c "import PIL, rarfile" 2>nul || python -m pip install --user pillow rarfile
start "" pythonw polices.py %*
