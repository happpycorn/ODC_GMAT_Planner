# 🚀 火箭軌道計算程式 (Rocket Trajectory Calculator)

本程式為高效能的火箭軌道計算軟體，底層採用多核心 (Multiprocessing) 與 JIT (Numba) 技術進行運算加速。

為了確保最佳的執行效能與最簡便的安裝體驗，本專案使用新一代極速套件管理工具 `uv`。您**不需要**繁瑣地設定虛擬環境，只需依照以下兩個步驟，即可一鍵啟動程式。

---

## ⚠️ 系統環境需求

請確認您的電腦已安裝 **Python 3.8 或以上版本**。
（若尚未安裝，請至 [Python 官方網站](https://www.python.org/downloads/) 下載安裝）

---

## 步驟一：安裝 `uv` 工具

請確保您的電腦已安裝 Python。接著，請打開終端機 (Mac) 或 命令提示字元/PowerShell (Windows)，輸入以下指令來安裝極速套件管理工具 `uv`：

```bash
pip install uv
```

---

## 步驟二：執行計算程式

本專案已將所有科學運算依賴寫入 `pyproject.toml` 中。請在終端機切換到本程式的資料夾後，直接輸入以下指令：

```bash
uv run main.py
```

---

## 📂 資料夾讀寫說明

* **輸入資料 (JSON)：** 請將需要計算的軌道參數 `configs.json` 檔案放置於 `configs` 資料夾內（如果沒有的話系統會自動建立）。
* **輸出結果 (TXT)：** 程式計算完成後，軌道結果會自動輸出 `output.txt` 至 `outputs` 資料夾中，可將其當做 script 輸入至 GMAT。
