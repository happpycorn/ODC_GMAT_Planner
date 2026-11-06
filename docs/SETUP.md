# 新電腦安裝：從 clone 到開 GUI

給隊友和備機用。一個 repo 裡有兩個工具：

| | 資料夾 | Python 環境 |
|---|---|---|
| 排位賽工具 | 專案根目錄 | `.venv`（numpy 1.26、numba 0.65、poliastro） |
| 金／銅牌賽工具 | `medal/` | `medal/.venv`（numpy 2.5、numba 0.67、torch） |
| 決賽 GUI | `gui/` | 用根目錄的 `.venv` 開，按鈕會自己切到對的資料夾 |

兩邊套件版本衝突，所以是**兩個獨立的 uv 專案**（各自的 `uv.lock`），不能合成一個 venv。
排位賽分數能重現就是靠根目錄這組版本，不要對任何一邊跑 `uv lock --upgrade` 或 `uv add`。

## 要先有的東西

- **網路**：只有安裝時要（兩邊合計下載約 2 GB）。比賽現場禁網路，備機一定要在賽前裝好。
- **git**。
- **GMAT R2026a**（排位賽驗證、金牌賽經緯高轉檔要用；其他功能沒有也能跑）。裝在路徑**全英文**的位置。
- `uv` 沒裝也沒關係，安裝腳本會問要不要幫你裝。

## 步驟

### Mac／Linux

```bash
git clone https://github.com/happpycorn/ODC_GMAT_Planner.git ODC_Program
```

```bash
cd ODC_Program && ./setup.sh
```

### Windows（PowerShell）

```powershell
git clone https://github.com/happpycorn/ODC_GMAT_Planner.git ODC_Program
cd ODC_Program
powershell -ExecutionPolicy Bypass -File setup.ps1
```

> `setup.ps1` 和 GUI 的 Windows 分支寫好時沒有 Windows 機器能測，只在 Mac 上用假環境測過停止工作、隨身碟清單、顯示檔案三段。
> 兩個工具也從沒在原生 Windows 上跑過（另一台開發機 Corn 用的是 WSL2，等於 Linux），第一次用請預留時間排錯；能用 WSL 就照 Mac／Linux 的步驟。

沒有網路、只有 USB 上的 bundle 時，把 clone 換成 `git clone <USB>/ODC_Final/backup/ODC_Program.bundle ODC_Program`（之後的 `uv sync` 還是要網路）。

### 安裝腳本做的事

1. 根目錄和 `medal/` 各跑一次 `uv sync --frozen --python 3.12`：照 lock 檔裝，不升級任何套件。
2. 沒有 `configs/local/config.json` 就建一份預設的，再把 GmatConsole 的路徑寫進它的 `local.gmat_console_path`。
   GMAT 的找法：`--gmat` 參數 → 已寫在 `config.json` 的路徑 → 環境變數 `GMAT_CONSOLE` → 常見安裝位置
   （Mac 的 `~/Documents/GMAT*`、`/Applications/GMAT*`；Linux 的 `~/software/GMAT`、`/opt/GMAT*`；Windows 的 `Program Files\GMAT*`）。
   都找不到就問一次，直接按 Enter 可以先跳過。
3. 體檢，每項印 ✓ 或 ✕：
   - GMAT 跑一個只建一艘太空船的小腳本，看報表有沒有數字
   - 排位賽 `odc.py test --quick -q`（約 3 分鐘）
   - 金牌賽 pytest 的快速子集（加 `--full-check` 跑完整的約 315 項）
   - GUI 在背景啟動、打兩支 API，再關掉

有 ✕ 時腳本的結束碼是 1，照那一行的提示修完重跑 `./setup.sh` 就好（重跑不會弄壞已經裝好的東西）。

選項：`--gmat <路徑>` 直接指定 GMAT、`--yes` 不問問題、`--no-check` 只安裝。

## 開 GUI

- Mac：Finder 雙擊 `gui/start.command`
- Windows：檔案總管雙擊 `gui\start.bat`
- 任何系統：在根目錄跑 `uv run python gui/app.py`

瀏覽器會打開 <http://127.0.0.1:8765>。用法看 [gui/README](../gui/README.md)。GUI 開著的時候不要關那個終端機視窗。

## 不用 GUI、直接下指令

- 排位賽：在根目錄 `uv run python odc.py ...`，照 [CONTEST_DAY](ranking/CONTEST_DAY.md)。`new-config` 記得帶 `--gmat-console <路徑>`。
- 金／銅牌賽：先 `cd medal`，再 `.venv/bin/python copilot.py final ...`（Windows 是 `.venv\Scripts\python.exe`），照 [CONTEST_DAY_FINAL](../medal/CONTEST_DAY_FINAL.md)。

兩邊各開一個終端機視窗，不要在同一個視窗裡切來切去，也不要在 `medal/` 裡用 `uv run python odc.py`。

## 常見問題

- **`uv sync` 說 lock 檔過期**：有人改了 `pyproject.toml` 卻沒更新 `uv.lock`。不要自己 `uv lock`，回報給負責的人。
- **GUI 顯示「找不到 GMAT」**：改 `configs/local/config.json` 的 `local.gmat_console_path`，或重跑 `./setup.sh --gmat <路徑>`，再重開 GUI。
- **GUI 顯示「找不到 medal/.venv/...」**：`cd medal && uv sync --frozen --python 3.12`。
- **Finder 雙擊 start.command 說找不到 uv**：`start.command` 會補上 `~/.local/bin`、Homebrew 的路徑；uv 裝在別處就把那個資料夾加進去。
