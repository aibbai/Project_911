@echo off
chcp 65001 > nul
cd /d "%~dp0"
set HTML_FILE=웹1차_실데이터연동_v1.html
python app_v1.py
if errorlevel 1 pause
