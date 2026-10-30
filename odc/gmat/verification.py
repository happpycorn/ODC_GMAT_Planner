"""執行 GMAT 驗證、保存報表並解析安全與收斂證據
主要入口為 run_gmat_verification。
"""
import os
import math
import time
import subprocess
import contextlib
import logging
import re
import hashlib
from pathlib import Path
from odc.pipeline.artifacts import (create_run_dir, save_mission, load_mission,
                                    write_json, file_digest, provenance)
from odc.physics.earth_gate import instrument_radius_report, analyze_radius_report, MIN_PERIAPSIS
from odc.runlog import log, setup as setup_logging


def run_gmat_verification(console_path: str, script_path: str, timeout_sec: float = 120.0,
                          artifacts_dir=None):
    """Verify an archived script copy with an isolated report destination.

    Only the archived copy gets report instrumentation and a maximum 60 s step.
    Each attempt keeps the exact executed script, stdout/stderr and result (including failure).
    """
    source = Path(script_path).resolve()
    folder = create_run_dir(artifacts_dir) if artifacts_dir else create_run_dir()
    report = folder / "GMAT_InterceptReport.txt"
    original_bytes = source.read_bytes()
    original = original_bytes.decode("ascii")
    if any(c in str(report) for c in ("'", "\n", "\r")) or not str(report).isascii():
        raise ValueError("GMAT 驗證輸出路徑須為 ASCII 且不可含單引號/換行。")
    executed, count = re.subn(
        r"(?m)^[ \t]*Report_Intercept\.Filename[ \t]*=[ \t]*'[^'\r\n]*'[ \t]*;",
        lambda _: f"Report_Intercept.Filename = '{report.as_posix()}';", original)
    if count != 1:
        raise ValueError("腳本需包含唯一的 Report_Intercept.Filename（本工具報表格式）。")
    radius_report = folder / "GMAT_RadiusReport.txt"
    executed = instrument_radius_report(executed, radius_report)
    script = folder / "executed.script"
    script.write_bytes(executed.encode("ascii"))
    started = time.perf_counter()
    result = _run_gmat_verification(console_path, str(script), timeout_sec,
                                    report_path=str(report), log_dir=folder)
    if result is not None:
        try:
            result.update(analyze_radius_report(radius_report, result["t_team_sec"]))
            log.info(f"🌍 攔截前最低半徑 {result['min_radius_before_intercept_km']:.6f} km，"
                     f"發生時刻 {result['min_radius_time_sec']:.6f} s；"
                     f"門檻 {MIN_PERIAPSIS:.6f} km（容許 −1 m）。")
        except (OSError, ValueError) as exc:
            result.update(earth_safe=False, min_radius_before_intercept_km=None,
                          min_radius_time_sec=None, min_periapsis_km=MIN_PERIAPSIS,
                          radius_acceptance_km=MIN_PERIAPSIS-1e-3, radius_error=str(exc))
            log.warning(f"🔴 半徑檢查失敗：{exc}；門檻 {MIN_PERIAPSIS:.6f} km，不可繳交。")
        if not result["earth_safe"]:
            log.warning("🔴 攔截前半徑安全關卡未通過，官方會判失格，**不可繳交**。")
    requires_dc = bool(re.search(r"(?m)^[ \t]*Target[ \t]+", original))
    checks_passed = bool(result and result["intercept_success"] and result["final_burn_legal"]
                         and result["earth_safe"]
                         and (not requires_dc or result["targeter_converged"]))
    if result is not None:
        result["checks_passed"] = checks_passed
    write_json(folder / "verification.json", {
        "schema_version": 1, "stage": "verification",
        "source_script": str(source), "source_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "executed_script": str(script), "executed_sha256": file_digest(script),
        "console_path": str(Path(console_path).expanduser().resolve()),
        "provenance": provenance(), "elapsed_sec": time.perf_counter() - started,
        "status": "completed" if result is not None else "failed", "result": result,
        "requires_dc": requires_dc, "checks_passed": checks_passed,
    })
    return result


def _run_gmat_verification(console_path: str, script_path: str, timeout_sec: float = 120.0,
                           *, report_path, log_dir):
    """
    呼叫 GmatConsole 用無頭批次模式 (--exit --run) 跑我們產生的 script，
    跑完直接讀回 GMAT 自己寫的 GMAT_InterceptReport.txt，回傳一個 dict。
    這一步失敗 (GMAT 沒裝/路徑不對/腳本有誤) 都不該讓整個程式當掉，只印警告後回傳 None，
    Python 端算出來的結果照樣有效、照樣會寫進 outputs/output.txt。
    """
    console_path = os.path.abspath(os.path.expanduser(console_path))
    (log_dir / "stdout.txt").write_text("", encoding="utf-8")
    (log_dir / "stderr.txt").write_text("", encoding="utf-8")
    if not os.path.exists(console_path):
        log.warning(f"⚠️ 找不到 GmatConsole ({console_path})，略過自動 GMAT 驗證。"
                    f"每次都要打 --gmat-console 太麻煩的話，可以在 config.json 裡加："
                    f'\n   "local": {{"gmat_console_path": "你的 GmatConsole 完整路徑"}}'
                    f"\n（這個設定只在你自己的 config.json 裡，不會跟著 git 到處跑）。"
                    f"不想跑 GMAT 驗證就用 --no-gmat 關掉這個提示。")
        return None

    bin_dir = os.path.dirname(console_path)

    # 關鍵防護 (2026-08-14 抓到的真 bug)：GMAT 執行失敗時 (腳本解析錯誤、跑到一半
    # 崩潰...) 不一定會清掉舊的報表檔——如果上一次執行 (可能是完全不同的 config/
    # 情境) 留下的報表檔還在，下面的 `os.path.exists(report_path)` 檢查會誤判成
    #「這次執行成功了」，讀到的其實是上一次殘留的舊資料，安靜地回傳一份看起來合
    # 理、實際上完全對不上這次腳本的假結果。實測抓到過：這次 script 因為某個非
    # ASCII 字元被 GMAT 解析器整個拒絕，但因為報表檔沒被清掉，讀回來的是前一次
    # (完全不同情境) 的殘留報表，main.py 印出一份看似正常、實則張冠李戴的驗證結果。
    # 修法：跑之前先把舊報表刪掉，讓「檔案存在」這件事只可能代表「這次真的寫出來
    # 了」，不會被殘留檔案騙過去。
    if os.path.exists(report_path):
        try:
            os.remove(report_path)
        except OSError as exc:
            log.warning(f"⚠️ 無法清除舊的報表檔 ({report_path}): {exc}，中止本次驗證。")
            return None

    log.info("\n🛰️  正在呼叫 GmatConsole 做無頭驗證...")
    try:
        result = subprocess.run(
            [console_path, "--exit", "--run", os.path.abspath(script_path)],
            cwd=bin_dir, capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired as exc:
        for name, data in (("stdout", exc.stdout), ("stderr", exc.stderr)):
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            (log_dir / f"{name}.txt").write_text(data or "", encoding="utf-8")
        log.warning(f"⚠️ GmatConsole 超過 {timeout_sec} 秒沒結束，放棄這次驗證。")
        return None
    except Exception as exc:
        log.warning(f"⚠️ 呼叫 GmatConsole 失敗: {exc}")
        return None

    stdout = result.stdout or ""
    (log_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (log_dir / "stderr.txt").write_text(result.stderr or "", encoding="utf-8")
    targeter_converged = "The Targeter converged!" in stdout

    # returncode 非 0 (腳本解析失敗、執行中崩潰...) 也要當失敗處理，不要只看報表
    # 檔存不存在——雖然上面已經先清掉舊檔案，這裡多一層檢查讓失敗訊息更明確、
    # 直接把 GMAT 自己回報的錯誤內容印出來，不用使用者自己去猜為什麼沒有報表。
    if result.returncode != 0:
        tail = "\n".join(stdout.strip().splitlines()[-15:])
        log.warning(f"⚠️ GmatConsole 執行失敗 (exit code {result.returncode})，GMAT 輸出末段：\n{tail}")
        return None

    if not os.path.exists(report_path):
        tail = "\n".join(stdout.strip().splitlines()[-15:])
        log.warning(f"⚠️ GMAT 執行完但找不到報表檔 ({report_path})，可能腳本執行有誤，GMAT 輸出末段：\n{tail}")
        return None

    with open(report_path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.read().strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        log.warning(f"⚠️ 報表檔 ({report_path}) 內容看起來不完整: {lines}")
        return None

    try:
        t_team, miss_km, success_flag, final_dv_mps, final_dv_legal, e1, e2, e3 = lines[-1].split()
        if not all(math.isfinite(float(v)) for v in lines[-1].split()):
            raise ValueError("non-finite GMAT report")
        return {
            "t_team_sec": float(t_team),
            "miss_km": float(miss_km),
            "intercept_success": bool(int(float(success_flag))),
            # GMAT 自己的 DC 可以自由調整這棒去命中瞄準點，這是它實際收斂後的真實
            # 大小，不是 Python 預測的那個值——InterceptSuccess 只看距離，不看這個，
            # 兩者要分開檢查。
            "final_burn_dv_mps": float(final_dv_mps),
            "final_burn_legal": bool(int(float(final_dv_legal))),
            "targeter_converged": targeter_converged,
            "report_path": report_path,
            # 最後一棒收斂後的 VNB 分量 (DC 版本才有意義；固定版本這三個值本來就是
            # 我們自己填的，讀回來只是拿來確認腳本真的照著寫死的值跑)。main.py 用
            # 這三個值產生「固定燃燒版本」的繳交腳本，見 script_generator() 的說明。
            "final_burn_vnb": (float(e1), float(e2), float(e3)),
        }
    except ValueError:
        log.warning(f"⚠️ 報表檔格式解析失敗: {lines[-1]!r}")
        return None


@contextlib.contextmanager
def patch_report_level(opt):
    """_replay_mission 的大塊報告壓成 DEBUG（失格候選不需要整頁任務規劃洗版；log 檔仍有）。"""
    old = getattr(opt, "_report_level", logging.INFO)
    opt._report_level = logging.DEBUG
    try:
        yield
    finally:
        opt._report_level = old
