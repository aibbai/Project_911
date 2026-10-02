@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0"

rem ============================================================
rem  챗봇(EXAONE) 포함 Flask 서버 실행
rem  - 가상환경이 없으면 자동 생성, 패키지가 없으면 자동 설치
rem  - requirements.txt 대신 아래 PKGS 목록 사용
rem ============================================================
set "ENV_NAME=exaone_chatbot"
set "PY_VER=3.10"
set PKGS=flask python-dotenv waitress requests "transformers>=4.54" accelerate

rem ---------- 1. conda 위치 찾기 ----------
set "CONDA_ROOT="
if defined CONDA_EXE for %%F in ("%CONDA_EXE%") do set "CONDA_ROOT=%%~dpF.."
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%LOCALAPPDATA%\anaconda3") do if not defined CONDA_ROOT if exist "%%~D\Scripts\conda.exe" set "CONDA_ROOT=%%~D"

rem ---------- 2. 이미 만든 환경 찾기 ----------
set "PY="
if defined CONDA_ROOT if exist "%CONDA_ROOT%\envs\%ENV_NAME%\python.exe" set "PY=%CONDA_ROOT%\envs\%ENV_NAME%\python.exe"
if not defined PY if exist "%USERPROFILE%\.conda\envs\%ENV_NAME%\python.exe" set "PY=%USERPROFILE%\.conda\envs\%ENV_NAME%\python.exe"
if not defined PY if not defined CONDA_ROOT if exist ".venv\Scripts\python.exe" set "PY=%CD%\.venv\Scripts\python.exe"

if defined PY goto :check
if defined CONDA_ROOT goto :make_conda
goto :make_venv

rem ---------- 3. 환경 만들기 (처음 한 번) ----------
:make_conda
echo [1/3] conda 환경 %ENV_NAME% 생성 중 - 처음 한 번만
"%CONDA_ROOT%\Scripts\conda.exe" create -y -n %ENV_NAME% python=%PY_VER% --override-channels -c conda-forge
set "PY=%CONDA_ROOT%\envs\%ENV_NAME%\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\.conda\envs\%ENV_NAME%\python.exe"
goto :check

:make_venv
echo [1/3] conda가 없어 .venv 가상환경 생성 중 - 처음 한 번만
py -%PY_VER% -m venv .venv 2>nul || python -m venv .venv
set "PY=%CD%\.venv\Scripts\python.exe"

rem ---------- 4. 패키지 확인 · 설치 ----------
:check
if not exist "%PY%" goto :fail
echo [2/3] 파이썬 : %PY%
"%PY%" -c "import torch, accelerate, flask, dotenv, waitress, requests, transformers as t; from packaging.version import Version as V; assert V(t.__version__) >= V('4.54')" 2>nul
if not errorlevel 1 goto :run

echo       필요한 패키지 설치 중 - 처음에는 몇 분 걸립니다
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"%PY%" -m pip install --upgrade %PKGS%
if errorlevel 1 goto :fail

rem ---------- 5. 서버 실행 ----------
:run
echo [3/3] 서버 실행
set "AUTO_OPEN_BROWSER=1"
"%PY%" app_integrated_v1.py
pause
exit /b 0

:fail
echo [오류] 환경 준비에 실패했습니다. 위 메시지를 확인하세요.
pause
exit /b 1
