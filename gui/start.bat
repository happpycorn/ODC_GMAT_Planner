@echo off
chcp 65001 >nul
rem 雙擊這個檔案就會開 GUI（會開一個命令提示字元視窗，GUI 用完再關掉它）。
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
cd /d "%~dp0.."
uv run python gui\app.py
if errorlevel 1 pause
