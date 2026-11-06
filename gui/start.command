#!/bin/zsh
# 雙擊這個檔案就會開 GUI（Finder 會開一個終端機視窗，GUI 用完再關掉它）。
cd "$(dirname "$0")/.." || exit 1
uv run python gui/app.py
