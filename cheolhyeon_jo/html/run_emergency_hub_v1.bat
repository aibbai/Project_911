@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 실행하면 브라우저에서 SEOUL EMERGENCY HUB 메인 화면이 열립니다
rem 화면 파일은 templates 폴더의 main.html / real_time.html / predict.html 을 사용
rem (base.html, header.html, footer.html 도 같은 templates 폴더에 있어야 함)
set HOME_FILE=main.html
set AUTO_OPEN_BROWSER=1
python app_integrated_v1.py
if errorlevel 1 pause
