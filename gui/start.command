#!/bin/zsh
# 雙擊這個檔案就會開 GUI（Finder 會開一個終端機視窗，GUI 用完再關掉它）。
# Finder 開的視窗不會讀 .zshrc，所以自己把 uv 的常見安裝位置加進 PATH。
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.." || exit 1
uv run python gui/app.py
