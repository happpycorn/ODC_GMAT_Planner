# 新電腦一鍵安裝（Windows PowerShell）：排位賽工具（根目錄）＋金／銅牌賽工具（medal/）＋GUI。
# 做的事跟 setup.sh 一樣。2026-11-06 寫好時沒有 Windows 機器、Mac 上也沒有 PowerShell，這份沒有實際跑過。
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#   powershell -ExecutionPolicy Bypass -File setup.ps1 -Gmat "C:\GMAT\R2026a\bin\GmatConsole.exe"
#   參數：-Gmat <路徑>、-Yes（不問問題）、-NoCheck（不跑體檢）、-FullCheck（金牌賽跑完整 pytest）
param([string]$Gmat = "", [switch]$Yes, [switch]$NoCheck, [switch]$FullCheck)

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
$Results = New-Object System.Collections.Generic.List[string]
function Ok($m)   { $Results.Add("✓ $m"); Write-Host "✓ $m" }
function Bad($m)  { $Results.Add("✕ $m"); Write-Host "✕ $m" }
function Step($m) { Write-Host ""; Write-Host "── $m" }
function Summary {
    Write-Host ""; Write-Host "================ 結果 ================"
    $Results | ForEach-Object { Write-Host $_ }
    if ($Results -match "^✕") { exit 1 } else { exit 0 }
}

# ---------------------------------------------------------------- uv
Step "uv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "找不到 uv。官方安裝指令：powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""
    if (-not $Yes) {
        $ans = Read-Host "現在幫你跑這行嗎？[y/N]"
        if ($ans -match "^[yY]") { powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex" }
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Host "沒有 uv 沒辦法繼續；裝好後重跑 setup.ps1"; exit 1 }
}
uv --version

# ---------------------------------------------------------------- 套件
Step "排位賽工具（根目錄）uv sync"
uv sync --frozen --python 3.12
if ($LASTEXITCODE -eq 0) { Ok "排位賽 venv（.venv）" } else { Bad "排位賽 uv sync 失敗" }

Step "金／銅牌賽工具（medal\）uv sync"
Push-Location medal
uv sync --frozen --python 3.12
$rc = $LASTEXITCODE
Pop-Location
if ($rc -eq 0) { Ok "金牌賽 venv（medal\.venv）" } else { Bad "金牌賽 uv sync 失敗" }

# ---------------------------------------------------------------- GMAT
Step "GMAT"
$Py = ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }
if (-not (Test-Path "configs\local\config.json") -and (Test-Path ".venv\Scripts\python.exe")) {
    & $Py -c "from odc.config.defaults import load_or_create_config; load_or_create_config()" *> $null
    if (Test-Path "configs\local\config.json") { Write-Host "已建立 configs\local\config.json（預設情境）" }
}
if (-not $Gmat) { $Gmat = (& $Py gui\gmat_path.py 2>$null | Select-Object -First 1) }
if ($Gmat -and -not (Test-Path -PathType Leaf $Gmat)) { Write-Host "設定裡的 GMAT 路徑不存在：$Gmat"; $Gmat = "" }
if (-not $Gmat -and -not $Yes) {
    $Gmat = (Read-Host "找不到 GmatConsole.exe。貼上完整路徑，直接按 Enter 跳過").Trim('"', ' ')
}
if ($Gmat -and (Test-Path -PathType Leaf $Gmat)) {
    if (Test-Path "configs\local\config.json") { & $Py gui\gmat_path.py --write $Gmat }
    Ok "GMAT 路徑：$Gmat"
} else {
    $Gmat = ""
    Bad "沒有 GMAT 路徑（排位賽步驟 6 與經緯高轉檔會失敗；之後重跑 setup.ps1 -Gmat <路徑>）"
}

if ($NoCheck) { Summary }

# ---------------------------------------------------------------- 體檢
$env:OMP_NUM_THREADS = "1"; $env:OPENBLAS_NUM_THREADS = "1"; $env:MKL_NUM_THREADS = "1"

Step "體檢：GMAT 能不能開"
if ($Gmat) {
    $T = Join-Path ([System.IO.Path]::GetTempPath()) ("odc_gmat_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $T | Out-Null
    $report = (Join-Path $T "probe.txt") -replace "\\", "/"
    "Create Spacecraft Probe;`nCreate ReportFile Rep;`nRep.Filename = '$report';`nBeginMissionSequence;`nReport Rep Probe.SMA;`n" |
        Set-Content -Encoding ascii (Join-Path $T "probe.script")
    Push-Location (Split-Path $Gmat)
    & $Gmat --exit --run (Join-Path $T "probe.script") *> (Join-Path $T "gmat.log")
    Pop-Location
    if ((Test-Path (Join-Path $T "probe.txt")) -and (Select-String -Quiet -Pattern "^[0-9]" (Join-Path $T "probe.txt"))) {
        Ok "GMAT 跑得起來"
    } else { Bad "GMAT 跑不起來（輸出在 $T\gmat.log）" }
} else { Bad "GMAT 沒設定，跳過" }

Step "體檢：排位賽 quick test（約 3 分鐘）"
uv run python odc.py test --quick -q
if ($LASTEXITCODE -eq 0) { Ok "排位賽 quick test" } else { Bad "排位賽 quick test 失敗" }

if ($FullCheck) { Step "體檢：金牌賽完整 pytest"; $MedalTests = @() }
else {
    Step "體檢：金牌賽 quick test"
    $MedalTests = @("tests/test_final_rules.py", "tests/test_final_copilot.py", "tests/test_official_io.py",
                    "tests/test_state_io.py", "tests/test_simultaneous.py")
}
if ($Gmat) { $env:GMAT_CONSOLE = $Gmat }
Push-Location medal
& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider @MedalTests
$rc = $LASTEXITCODE
Pop-Location
if ($rc -eq 0) { Ok "金牌賽 pytest" } else { Bad "金牌賽 pytest 有失敗（完整跑時 test_rule_map::test_rule_ranges_sample_unchanged 是已知的浮點假失敗）" }

Step "體檢：GUI 能不能啟動"
$Port = 8799
$gui = Start-Process -FilePath uv -ArgumentList "run", "python", "gui\app.py", "--no-browser", "--port", "$Port" -PassThru -WindowStyle Hidden
$GuiOk = $false
for ($i = 0; $i -lt 30 -and -not $GuiOk; $i++) {
    Start-Sleep -Seconds 1
    try {
        $m = Invoke-RestMethod -TimeoutSec 5 "http://127.0.0.1:$Port/api/medal/overview"
        $r = Invoke-RestMethod -TimeoutSec 5 "http://127.0.0.1:$Port/api/ranking/overview?name=config"
        if ($m.ok -and $r.ok -and $m.drl_ok) { $GuiOk = $true }
    } catch { }
}
# uv 會再開一個 python 子行程，整棵一起停
taskkill /PID $gui.Id /T /F *> $null
if ($GuiOk) { Ok "GUI 啟動（http://127.0.0.1:8765，雙擊 gui\start.bat 開）" } else { Bad "GUI 啟動失敗（手動跑 uv run python gui\app.py 看錯誤）" }

Summary
