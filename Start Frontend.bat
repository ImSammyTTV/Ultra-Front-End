@echo off
rem Starts Game Frontend.exe (helper + fullscreen window in one program). Alt+F4 to close.
rem Rebuild the exe after changing server.py or frontend.py:  python -m PyInstaller "Game Frontend.spec"
start "" "%~dp0Game Frontend.exe"
