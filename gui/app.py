"""決賽當天用的本機 GUI：排位賽（專案根目錄）與金／銅牌賽（medal/）照手冊一步一步做。

只用標準函式庫，不需網路。每個按鈕在背後跑的就是手冊上的同一條指令，畫面會印出指令全文，
GUI 壞掉時照抄到終端機一樣能做。

    uv run python gui/app.py          # 或直接雙擊 gui/start.command
    瀏覽器開 http://127.0.0.1:8765
"""
import argparse
import codecs
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GUI_DIR))
import gmat_path  # noqa: E402
from medal_orbits import SIDES, epoch_utc, norm, orbit_summary, propagate, utc_text  # noqa: E402

WINDOWS = os.name == "nt"
DRL = Path(os.environ.get("ODC_DRL_DIR", ROOT / "medal")).resolve()
GMAT, GMAT_SOURCE = gmat_path.resolve()
GMAT = GMAT or "GmatConsole"  # 找不到時照樣顯示指令，畫面會標紅
EARTH_R_KM = 6378.137

ODC = ["uv", "run", "python", "odc.py"]
# Windows 的 venv 在 Scripts\，而且相對路徑的執行檔不會照 cwd 找，所以用絕對路徑
DRL_PYTHON = DRL / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
DRLPY = [str(DRL_PYTHON)] if WINDOWS else [".venv/bin/python"]
RUNS = ROOT / "outputs" / "runs"
DAY = Path(os.environ.get("ODC_DAY_DIR", DRL / "day")).resolve()  # 測 GUI 時改到別處，比賽當天用預設
DAY_BASE = DAY.parent  # 金牌賽頁可以換設定檔（資料夾）名稱，都放在這一層
DAY_DEFAULT = DAY.name
DAY_ARG = os.path.relpath(DAY, DRL) if DAY.is_relative_to(DRL) else str(DAY)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ELEMENTS = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")
# 範本（configs/shared/ranking_round.json）的佔位值；當天還是這些數字代表忘了換
PLACEHOLDER_RULES = {"T_MAX_SEC": 40000.0, "k_t": 0.0001, "C_t": 25000.0, "k_v": 0.002, "C_v": 1500.0}
# 沒填 GMAT_EPOCH／GMAT_SPACECRAFT 時繳交腳本裡的預設值（odc/config/gmat_env.py）
SUBMIT_DEFAULTS = {"DateFormat": "TAIModJulian", "Epoch": "21545", "DryMass": "850", "Cd": "2.2", "Cr": "1.8",
                   "DragArea": "6", "SRPArea": "8"}


class UserError(Exception):
    """要原樣顯示給使用者看的錯誤。"""


# ---------------------------------------------------------------- 背景工作

class Job:
    def __init__(self, key, title, cmd, cwd):
        self.id = f"{int(time.time() * 1000):x}"
        self.key, self.title, self.cmd, self.cwd = key, title, cmd, Path(cwd)
        self.started, self.ended, self.rc = time.time(), None, None
        self.lines, self.proc, self.stopped = [], None, False
        self.live = ""  # 還沒換行的最後一行（進度條用 \r 原地更新）

    def info(self, since=0):
        return {"id": self.id, "key": self.key, "title": self.title,
                "command": f"cd {shlex.quote(str(self.cwd))} && {shlex.join(self.cmd)}",
                "started": self.started, "ended": self.ended, "rc": self.rc,
                "running": self.ended is None, "stopped": self.stopped,
                "lines": self.lines[since:], "total": len(self.lines), "live": self.live}


JOBS = {}
JOBS_LOCK = threading.Lock()


def start_job(key, title, cmd, cwd):
    with JOBS_LOCK:
        for job in JOBS.values():
            if job.key == key and job.ended is None:
                raise UserError(f"「{job.title}」還在跑，等它結束或先按停止")
    job = Job(key, title, [str(c) for c in cmd], cwd)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    # 自成一個行程群組，停止時連 uv 底下的 python 一起停
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True})
    try:
        job.proc = subprocess.Popen(job.cmd, cwd=job.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, **group)
    except FileNotFoundError as exc:
        raise UserError(f"找不到程式：{exc.filename}（在 {cwd}）")

    def pump():
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        partial, after_cr = "", False
        while True:
            chunk = job.proc.stdout.read1(65536)
            for piece in re.split(r"(\r\n|\n|\r)", decoder.decode(chunk, final=not chunk)):
                if piece in ("\n", "\r\n"):
                    if partial or not after_cr:
                        job.lines.append(partial)
                    elif job.live:
                        job.lines.append(job.live)  # \r\n 被拆在兩個 chunk 中間
                    partial, after_cr, job.live = "", False, ""
                elif piece == "\r":
                    partial, after_cr = "", True
                elif piece:
                    partial += piece
                    after_cr = False
                    job.live = partial
            if not chunk:
                break
        if partial:
            job.lines.append(partial)
        job.live = ""
        job.rc = job.proc.wait()
        job.ended = time.time()

    threading.Thread(target=pump, daemon=True).start()
    with JOBS_LOCK:
        JOBS[job.id] = job
    return job


def stop_job(job_id):
    job = JOBS.get(job_id)
    if job is None or job.ended is not None:
        return
    job.stopped = True
    try:
        if WINDOWS:
            # Windows 沒有 killpg：先送 Ctrl+Break 給整個群組，停不下來再 terminate
            job.proc.send_signal(signal.CTRL_BREAK_EVENT)
            time.sleep(1.5)
            if job.proc.poll() is None:
                job.proc.terminate()
        else:
            os.killpg(job.proc.pid, signal.SIGINT)
            time.sleep(1.5)
            if job.proc.poll() is None:
                os.killpg(job.proc.pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def job_output(job_id):
    job = JOBS.get(job_id)
    return "\n".join(job.lines) if job else ""


# ---------------------------------------------------------------- 共用小工具

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def check_name(name, what="名稱"):
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise UserError(f"{what}只能用英文、數字、. _ -：{name!r}")
    return name


def num(value, what):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise UserError(f"{what} 不是數字：{value!r}")
    if x != x or x in (float("inf"), float("-inf")):
        raise UserError(f"{what} 不是有限數字")
    return x


def num_text(value, what):
    """傳給 CLI 的數字保留使用者原本的寫法（例如 1e-4），只檢查能不能轉。"""
    num(value, what)
    return str(value).strip()


def tail(path, n=60):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readlines()[-n:]
    except FileNotFoundError:
        return []


def free_name(base, parent):
    if not (parent / base).exists():
        return base
    i = 2
    while (parent / f"{base}{i}").exists():
        i += 1
    return f"{base}{i}"


# ---------------------------------------------------------------- 排位賽

def cfg_path(name):
    return ROOT / "configs" / "local" / f"{check_name(name, '設定檔名稱')}.json"


def cfg_rel(name):
    return f"configs/local/{check_name(name, '設定檔名稱')}.json"


def template():
    return read_json(ROOT / "configs" / "shared" / "ranking_round.json")


def orbit_warnings(orbit, label):
    out = []
    try:
        sma, ecc, ta = float(orbit["SMA"]), float(orbit["ECC"]), float(orbit["TA"])
    except (KeyError, TypeError, ValueError):
        return [f"{label} 根數不完整"]
    if ecc > 1 and sma > 0:
        out.append(f"{label}：ECC > 1 是雙曲線，SMA 應該是負的")
    if ecc < 1 and sma < 0:
        out.append(f"{label}：ECC < 1 是橢圓，SMA 應該是正的")
    if ecc < 1 and sma * (1 - ecc) < EARTH_R_KM:
        out.append(f"{label}：近地點 {sma * (1 - ecc):.1f} km 在地球裡面，檢查 SMA／ECC")
    if ecc > 1 and abs(ta) > 0:
        import math
        lim = math.degrees(math.acos(-1 / ecc))
        t = ((ta + 180) % 360) - 180
        if abs(t) >= lim:
            out.append(f"{label}：雙曲線 |TA| 必須 < {lim:.2f}°（現在等效 {t:.2f}°）")
    return out


def ranking_config(name):
    path = cfg_path(name)
    if not path.exists():
        return {"exists": False, "name": name, "path": cfg_rel(name)}
    cfg = read_json(path)
    tpl = template()
    rules, strategy = cfg.get("rules", {}), cfg.get("strategy", {})
    placeholder_orbit = all(cfg.get(k) == tpl.get(k) for k in ("orbit_A", "orbit_B"))
    placeholder_rules = [k for k, v in PLACEHOLDER_RULES.items() if rules.get(k) == v]
    warnings = orbit_warnings(cfg.get("orbit_A", {}), "A") + orbit_warnings(cfg.get("orbit_B", {}), "B")
    return {"exists": True, "name": name, "path": cfg_rel(name),
            "orbit_A": cfg.get("orbit_A"), "orbit_B": cfg.get("orbit_B"), "rules": rules,
            "epoch": strategy.get("GMAT_EPOCH", ""), "epoch_format": strategy.get("GMAT_EPOCH_FORMAT", ""),
            "spacecraft": strategy.get("GMAT_SPACECRAFT", {}),
            "seed": cfg.get("optimization", {}).get("SEED"), "maxiter": cfg.get("optimization", {}).get("MAXITER"),
            "gmat": cfg.get("local", {}).get("gmat_console_path"),
            "placeholder_orbit": placeholder_orbit, "placeholder_rules": placeholder_rules,
            "warnings": warnings}


def save_ranking_config(body):
    name = body.get("name")
    path = cfg_path(name)
    if not path.exists():
        raise UserError("設定檔還沒建，先按「建立設定檔」")
    cfg = read_json(path)
    for key in ("orbit_A", "orbit_B"):
        if key in body:
            cfg[key] = {e: num(body[key].get(e), f"{key}.{e}") for e in ELEMENTS}
    strategy = cfg.setdefault("strategy", {})
    if "epoch" in body:
        epoch, fmt = str(body.get("epoch") or "").strip(), str(body.get("epoch_format") or "").strip()
        if epoch and not fmt:
            raise UserError("填了曆元就要填 DateFormat（照題目 Script，例如 UTCGregorian）")
        if epoch:
            strategy["GMAT_EPOCH"], strategy["GMAT_EPOCH_FORMAT"] = epoch, fmt
        else:
            strategy.pop("GMAT_EPOCH", None)
            strategy.pop("GMAT_EPOCH_FORMAT", None)
    if "spacecraft" in body:
        sc = {k: num(v, k) for k, v in body["spacecraft"].items() if str(v).strip() != ""}
        if sc:
            strategy["GMAT_SPACECRAFT"] = sc
        else:
            strategy.pop("GMAT_SPACECRAFT", None)
    if "t_max_sec" in body:
        t = num(body["t_max_sec"], "T_MAX_SEC")
        if t <= 0:
            raise UserError("T_MAX_SEC 要大於 0")
        cfg.setdefault("rules", {})["T_MAX_SEC"] = t
    write_json(path, cfg)
    return ranking_config(name)


def make_variant(body):
    name, kind = body.get("name"), body.get("kind")
    src = cfg_path(name)
    if not src.exists():
        raise UserError("原設定檔不存在")
    cfg = read_json(src)
    if kind == "s1":
        new = f"{name}-s1"
        cfg.setdefault("optimization", {})["SEED"] = 1
    elif kind == "fast":
        new = f"{name}-fast"
        cfg.setdefault("optimization", {})["MAXITER"] = 300
        cfg.setdefault("strategy", {})["PRIMER_GUIDED_RESEARCH"] = False
    else:
        raise UserError(f"不認得的變體：{kind}")
    dst = cfg_path(new)
    if dst.exists():
        raise UserError(f"{cfg_rel(new)} 已經存在；要重做就先把它移走")
    write_json(dst, cfg)
    return {"name": new}


def ranking_command(body):
    """把畫面上的按鈕對到手冊上的指令；只接受這裡列出的動作。"""
    act, name = body.get("action"), body.get("name")
    cfg = cfg_rel(name) if name else None
    if act == "new-config":
        if cfg_path(name).exists():
            raise UserError(f"{cfg} 已經存在（new-config 不覆蓋）。直接往下填就好")
        return "建立設定檔", ODC + ["new-config", name, "--gmat-console", GMAT]
    if act == "tmax":
        flag = {"center": "--boundary-km", "alt": "--boundary-alt-km"}[body.get("mode")]
        cmd = ODC + ["tmax", "--config", cfg, flag, num_text(body.get("boundary"), "邊界")]
        if body.get("write"):
            cmd.append("--write")
        return "算 T_max" + ("並寫入" if body.get("write") else ""), cmd
    if act == "scoring":
        cmd = ODC + ["scoring", "--config", cfg,
                     "--kt", num_text(body.get("kt"), "k_t"), "--kt-unit", body.get("kt_unit") or "1/s",
                     "--Ct", num_text(body.get("Ct"), "C_t"), "--Ct-unit", body.get("Ct_unit") or "s",
                     "--kv", num_text(body.get("kv"), "k_v"), "--kv-unit", body.get("kv_unit"),
                     "--Cv", num_text(body.get("Cv"), "C_v"), "--Cv-unit", body.get("Cv_unit"),
                     "--Cr", num_text(body.get("Cr"), "C_r")]
        if not body.get("kv_unit") or not body.get("Cv_unit"):
            raise UserError("k_v、C_v 的單位一定要選")
        if str(body.get("ref_dv") or "").strip():
            cmd += ["--ref-dv", num_text(body["ref_dv"], "參考解 Δv"), "--ref-dv-unit", body.get("ref_dv_unit") or "m/s",
                    "--ref-t", num_text(body.get("ref_t"), "參考解攔截時刻")]
        if body.get("write"):
            cmd.append("--write")
        return "計分參數" + ("寫入" if body.get("write") else "試算"), cmd
    if act == "check":
        return "體檢 check", ODC + ["check", cfg]
    if act == "feasibility":
        return "體檢 feasibility", ODC + ["feasibility", cfg]
    if act == "solve":
        run = check_name(body.get("run"), "執行目錄")
        if (RUNS / run).exists():
            raise UserError(f"outputs/runs/{run} 已經存在；換一個名字（例如 -2）")
        return f"求解 {run}", ODC + ["solve", cfg, "--run-dir", f"outputs/runs/{run}", "-q"]
    if act == "retarget":
        run = check_name(body.get("run"), "執行目錄")
        if not (RUNS / run / "mission.json").exists():
            raise UserError(f"outputs/runs/{run}/mission.json 不存在；求解還沒成功")
        rt = free_name(f"{run}-rt", RUNS)
        cmd = ODC + ["retarget", f"outputs/runs/{run}/mission.json", "--config", cfg, "--run-dir", f"outputs/runs/{rt}"]
        if str(body.get("burn", "")).strip() != "":
            cmd += ["--retarget-burn", str(int(num(body["burn"], "棒號")))]
        return f"重瞄準 {rt}", cmd
    if act == "verify":
        rt = check_name(body.get("rt"), "重瞄準目錄")
        if not (RUNS / rt / "output_submit.txt").exists():
            raise UserError(f"outputs/runs/{rt}/output_submit.txt 不存在；重瞄準還沒通過")
        base = rt[:-3] if rt.endswith("-rt") else rt
        vd = free_name(f"{base}-verify", RUNS)
        return f"GMAT 重驗 {vd}", ODC + ["verify", f"outputs/runs/{rt}/output_submit.txt", "--config", cfg,
                                         "--run-dir", f"outputs/runs/{vd}"]
    raise UserError(f"不認得的動作：{act}")


def run_summary(run):
    d = RUNS / run
    out = {"run": run, "exists": d.exists()}
    rj = d / "run.json"
    if rj.exists():
        info = read_json(rj)
        out["status"] = info.get("status")
        out["config"] = info.get("arguments", {}).get("config")
    if (d / "no_legal_route.json").exists():
        out["no_legal_route"] = True
    mj = d / "mission.json"
    if mj.exists():
        m = read_json(mj)["mission_info"]
        out.update(score=m.get("score"), disqualified=m.get("disqualified"), dq_reasons=m.get("dq_reasons"),
                   num_burns=m.get("num_burns"), total_dv=m.get("total_dv_mps"), T_team=m.get("T_team"),
                   miss_km=m.get("miss_km"))
    out["log_tail"] = tail(d / "run.log", 40)
    return out


def verify_passed(vd):
    log = "".join(tail(RUNS / vd / "run.log", 400))
    return "GMAT 獨立驗證通過" in log


def checklist(rt, name):
    """手冊步驟 7 的清單；能自動判斷的直接打勾或打叉。"""
    rj = RUNS / rt / "retarget.json"
    if not rj.exists():
        raise UserError(f"{rt}/retarget.json 不存在")
    r = read_json(rj)
    c = read_json(cfg_path(name))["rules"]
    x = r["result"]
    g = x["retargeted"]["legality"]
    v = x["fixed_script_verification"]
    burns = g["burn_dv_mps"]
    T = x["retargeted"]["t_team_sec"]
    base = rt[:-3] if rt.endswith("-rt") else rt
    vds = sorted(p.name for p in RUNS.glob(f"{base}-verify*") if p.is_dir())
    vd_ok = [vd for vd in vds if verify_passed(vd)]
    max_burn, cap = max(burns), c["MAX_DV_MPS"] - 1.0
    total_cap = c.get("MAX_TOTAL_DV_MPS") or 0
    alt = v["min_radius_before_intercept_km"] - EARTH_R_KM
    left = c["T_MAX_SEC"] - T
    placeholder = [k for k, val in PLACEHOLDER_RULES.items() if c.get(k) == val]
    # 11-07 彩排漏填曆元與太空船參數，官方設定下差 23 km；這裡讀繳交腳本實際寫進去的值
    sp = RUNS / rt / "output_submit.txt"
    script = sp.read_text(encoding="utf-8", errors="replace") if sp.exists() else ""
    env = {}
    for k in SUBMIT_DEFAULTS:
        m = re.search(r"SC_Human\." + k + r" = '?([^';]*)", script)
        if m:
            env[k] = m.group(1).strip()
    env_default = [k for k, val in SUBMIT_DEFAULTS.items() if env.get(k) == val]
    env_label = "曆元與太空船參數照題目 Script（不是預設值）"
    items = [
        ("狀態 accepted、失格 False、間隔違規 0",
         r["status"] == "accepted" and not g["disqualified"] and g["penalty_count"] == 0,
         f"狀態 {r['status']}｜失格 {g['disqualified']} {g['dq_reasons']}｜間隔違規 {g['penalty_count']}"),
        (f"最大單棒 ≤ {cap:g} m/s", max_burn <= cap, f"{len(burns)} 棒，最大 {max_burn:.5f} m/s"),
        (f"總 Δv ≤ {total_cap:g} m/s", (not total_cap) or g["total_dv_mps"] <= total_cap, f"{g['total_dv_mps']:.4f} m/s"),
        ("d_min 與 GMAT Δr 都 < 4 km、命中 True",
         x["retargeted"]["d_min_km"] < 4 and v["miss_km"] < 4 and bool(v["intercept_success"]),
         f"全攝動 d_min {x['retargeted']['d_min_km']:.3f} km｜GMAT Δr {v['miss_km']:.3f} km｜命中 {v['intercept_success']}"),
        ("離 T_max ≥ 300 s", left >= 300, f"T_team {T:.3f} s，還剩 {left:.0f} s"),
        ("攔截前最低高度 > 100 km", alt > 100, f"{alt:.0f} km"),
        ("T_MAX_SEC、k_t/C_t/k_v/C_v 不是範本佔位值", not placeholder,
         "還是佔位值：" + "、".join(placeholder) if placeholder else "都已換過（數字對不對仍要人工對官方）"),
        (env_label, bool(env) and "Epoch" not in env_default,
         ("、".join(f"{k} {v}" for k, v in env.items()) or "讀不到 output_submit.txt")
         + ("｜Epoch 還是預設 21545：回步驟 1 補曆元與太空船參數，只重跑步驟 6" if "Epoch" in env_default
            else "｜跟題目 Script 逐項核對" if env else "")),
        ("verify 印了 ✅ GMAT 獨立驗證通過", bool(vd_ok), "、".join(vd_ok) if vd_ok else ("沒有通過的 verify：" + ("、".join(vds) or "還沒跑"))),
    ]
    # 彩排用佔位題時，佔位值那項只提醒、不擋存檔；當天的 ranking 一定要擋。
    # 曆元那項只提醒：題目真的沒給曆元時預設值是對的，由下面「已逐字元核對」那格人工確認
    rows = [{"label": a, "ok": bool(b), "detail": d,
             "blocking": not ((a.startswith("T_MAX_SEC") and name != "ranking") or a == env_label)}
            for a, b, d in items]
    return {"rt": rt, "score": g["official_score"], "verify_dirs": vd_ok, "items": rows,
            "all_ok": all(r["ok"] or not r["blocking"] for r in rows)}


def ranking_overview(name):
    cfg = ranking_config(name)
    # 同一題的設定檔（ranking、ranking-s1、ranking-fast）跑出來的結果放在一起看
    base = re.sub(r"-(s1|fast)$", "", name)
    family = {cfg_rel(base), cfg_rel(f"{base}-s1"), cfg_rel(f"{base}-fast")}
    runs = []
    if RUNS.exists():
        for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime):
            if not d.is_dir():
                continue
            try:
                used = read_json(d / "run.json").get("arguments", {}).get("config")
            except (OSError, ValueError):
                used = None  # 剛開跑、run.json 還沒寫：先列出來
            if used is not None and used not in family:
                continue
            kind = "verify" if "-verify" in d.name else "rt" if re.search(r"-rt\d*$", d.name) else "solve"
            item = {"name": d.name, "kind": kind, "mtime": d.stat().st_mtime}
            if kind == "solve":
                item.update({k: v for k, v in run_summary(d.name).items() if k != "log_tail"})
            elif kind == "rt":
                rj = d / "retarget.json"
                if rj.exists():
                    r = read_json(rj)
                    item["status"] = r.get("status")
                    try:
                        item["score"] = r["result"]["retargeted"]["legality"]["official_score"]
                    except (KeyError, TypeError):
                        pass
            else:
                item["passed"] = verify_passed(d.name)
            runs.append(item)
    choices = sorted(f.stem for f in (ROOT / "configs" / "local").glob("*.json") if f.stem != "config" and NAME_RE.match(f.stem))
    return {"config": cfg, "config_choices": choices, "runs": runs, "gmat": GMAT, "gmat_ok": Path(GMAT).is_file(), "gmat_source": GMAT_SOURCE}


def removable_drives():
    """Windows 的可移除磁碟代號（E: 之類）。"""
    import ctypes
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    drives = []
    for i in range(26):
        root = f"{chr(65 + i)}:\\"
        if mask >> i & 1 and kernel.GetDriveTypeW(root) == 2:  # DRIVE_REMOVABLE
            drives.append(root)
    return drives


def volumes():
    """看得到、可以寫的隨身碟：{顯示名稱: 掛載路徑}。"""
    if WINDOWS:
        mounts = [Path(d) for d in removable_drives()]
    elif sys.platform == "darwin":
        mounts = sorted(Path("/Volumes").iterdir()) if Path("/Volumes").exists() else []
    else:
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        mounts = []
        for parent in (Path("/media") / user, Path("/run/media") / user):
            if user and parent.is_dir():
                mounts += sorted(parent.iterdir())
    vols = {}
    for p in mounts:
        if p.is_dir() and not p.is_symlink() and os.access(p, os.W_OK):
            vols[p.drive if WINDOWS else p.name] = str(p)
    return vols


def reveal(target):
    """在檔案管理員裡顯示這個檔案。"""
    if WINDOWS:
        subprocess.run(["explorer", f"/select,{target}"], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(target)], check=False)
    else:
        subprocess.run(["xdg-open", str(target.parent)], check=False)


def save_to_usb(body):
    rt = check_name(body.get("rt"), "重瞄準目錄")
    vol = body.get("volume")
    score = num(body.get("score"), "分數")
    tag = check_name(body.get("tag") or rt.split("-rt")[0], "檔名前綴")
    src = RUNS / rt / "output_submit.txt"
    if not src.exists():
        raise UserError(f"{rt}/output_submit.txt 不存在")
    if vol == "__local__":
        dest = ROOT / "outputs" / "ODC_Final" / "ranking"
    else:
        vols = volumes()
        if vol not in vols:
            raise UserError(f"找不到隨身碟 {vol!r}；重新整理清單")
        dest = Path(vols[vol]) / "ODC_Final" / "ranking"
    dest.mkdir(parents=True, exist_ok=True)
    prefix = f"{tag}_{score:.2f}"
    copied = [shutil.copy2(src, dest / f"{prefix}_output_submit.txt")]
    for vd in body.get("verify_dirs") or []:
        gm = RUNS / check_name(vd) / "gmat"
        for rep in ("GMAT_InterceptReport.txt", "GMAT_RadiusReport.txt"):
            if (gm / rep).exists():
                copied.append(shutil.copy2(gm / rep, dest / f"{prefix}_{rep}"))
        break
    return {"dest": str(dest), "files": [str(p) for p in copied]}


# ---------------------------------------------------------------- 金／銅牌賽

def day_file(name):
    name = os.path.basename(str(name or ""))
    if not name or name.startswith(".") or "/" in name or "\\" in name:
        raise UserError(f"檔名不合法：{name!r}")
    return DAY / name


def day_rel(name):
    return f"{DAY_ARG}/{day_file(name).name}"


def medal_files():
    if not DAY.exists():
        return []
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime}
            for p in sorted(DAY.iterdir(), key=lambda p: p.stat().st_mtime) if p.is_file()]


MEDAL_LOCK = threading.Lock()


def read_medal_session():
    # CLI 直接寫 session；輪詢恰好遇到寫入中時，短暫重讀，避免把半份 JSON 當成壞檔。
    for attempt in range(4):
        try:
            return read_json(DAY / "session.json")
        except (OSError, ValueError) as exc:
            if attempt == 3:
                raise UserError("整場紀錄暫時讀不到。請等工作輸出完成後重新整理；仍不行就到備援工具檢查 session.json 與備份檔。") from exc
            time.sleep(0.02)


def medal_names(body=None):
    body = body or {}
    names = str(body.get("names") or "").strip()
    if names:
        return names
    return ",".join(f"{side}={str((body.get(side) or {}).get('name') or '').strip()}"
                    for side, _ in SIDES if str((body.get(side) or {}).get("name") or "").strip())


def medal_epoch_command(cmd):
    """initial.json 的 epoch 已正規化成 ISO，CLI 直接讀；保留這個函式只為了不動呼叫端。"""
    return cmd


def write_announce_form(body):
    """公告原值留底、換單位、二體念回；確認警告前不動任何檔案。"""
    errors, warnings, state, summaries, epochs = {}, [], {}, {}, {}

    def number(value, field, label):
        try:
            return num(value, label)
        except UserError:
            errors[field] = f"{label}要填數字，請回頭核對投影片。"
            return 0.0

    def unit(value, field, choices):
        if value not in choices:
            errors[field] = "這個單位無法辨認，請重新選擇。"
            return next(iter(choices.values()))
        return choices[value]

    dv = number(body.get("dv_lim"), "dv_lim", "ΔV_lim") * unit(body.get("dv_unit", "m/s"), "dv_unit", {"m/s": 1, "km/s": 1000})
    radius = number(body.get("rcap"), "rcap", "R_cap") * unit(body.get("rcap_unit", "km"), "rcap_unit", {"km": 1, "m": 0.001})
    window = number(body.get("tround"), "tround", "T_round") * unit(body.get("time_unit", "sec"), "time_unit", {"sec": 1, "min": 60, "hour": 3600})
    bounds = []
    for field, label in (("lo", "安全空域下限"), ("hi", "安全空域上限")):
        val = number(body.get(field), field, label)
        factor, offset = unit(body.get(f"{field}_unit", body.get("safe_unit", "sma")), f"{field}_unit",
                              {"sma": (1, 0), "alt_km": (1, EARTH_R_KM), "alt_m": (0.001, EARTH_R_KM)})
        bounds.append(val * factor + offset)
    if bounds[0] >= bounds[1]:
        errors["lo"] = errors["hi"] = "安全空域下限要小於上限，請核對投影片。"
    if bounds[0] < EARTH_R_KM:
        errors["lo"] = "換算後的下限低於地表，請核對數字與高度／半長軸單位。"
    for field, val, label in (("dv_lim", dv, "ΔV_lim"), ("rcap", radius, "R_cap"), ("tround", window, "T_round")):
        if not math.isfinite(val):
            errors[field] = f"{label}換算後太大，請核對數字與單位。"
        if val <= 0:
            errors.setdefault(field, f"{label}要大於零，請核對投影片。")
    for side, label in SIDES:
        raw = body.get(side) or {}
        r_factor = unit(raw.get("r_unit", "km"), f"{side}.r_unit", {"km": 1, "m": 0.001})
        v_factor = unit(raw.get("v_unit", "km/s"), f"{side}.v_unit", {"km/s": 1, "m/s": 0.001})
        r = [number(raw.get(key), f"{side}.{key}", f"{label} {key}") * r_factor for key in ("X", "Y", "Z")]
        v = [number(raw.get(key), f"{side}.{key}", f"{label} {key}") * v_factor for key in ("VX", "VY", "VZ")]
        if not all(math.isfinite(val) for val in r + v):
            errors[f"{side}.X"] = f"{label}換算後的數字太大，請核對位置、速度與單位。"
        original_epoch = str(raw["epoch"]) if raw.get("epoch") is not None else ""
        try:
            epochs[side] = epoch_utc(original_epoch)
        except (ValueError, OverflowError):
            epochs[side] = None
            errors[f"{side}.epoch"] = f"{label}時間看不懂。請填 GMAT 日期、ISO 日期，或 GMAT UTCModJulian 數字。"
        # initial.json 存正規化的 UTC（ISO），medal 的解析器原生就讀得懂；原字串留在 announce_input.json
        state[side] = {"r_km": r, "v_kms": v}
        if epochs.get(side) is not None:
            state[side]["epoch"] = utc_text(epochs[side])
        try:
            summaries[side] = {**orbit_summary(r, v), "epoch_utc": utc_text(epochs[side])}
            if any(summaries[side][key] is None for key in ("radius_km", "speed_kms", "perigee_alt_km")):
                errors[f"{side}.X"] = f"{label}軌道無法用這些數字計算，請核對位置、速度與單位。"
        except (OverflowError, ValueError, ZeroDivisionError):
            errors[f"{side}.X"] = f"{label}軌道算不出來，請核對位置、速度與單位。"
    if (epochs["pursuer"] is None) != (epochs["evader"] is None):
        for side, _ in SIDES:
            errors.setdefault(f"{side}.epoch", "只有一艘填時間。請兩艘都填，或兩艘都留空。")
    if errors:
        return {"valid": False, "field_errors": errors, "error": "請先修正紅框，再按存檔。"}
    for side, label in SIDES:
        summary = summaries[side]
        if not 6500 <= summary["radius_km"] <= 50000:
            warnings.append(f"看起來{label}距地心 {summary['radius_km']:.3f} km 不在 6,500–50,000 km，可能是位置單位或小數點抄錯，請核對投影片。")
        if not 1 <= summary["speed_kms"] <= 11:
            warnings.append(f"看起來{label}速度 {summary['speed_kms']:.6f} km/s 不在 1–11 km/s，可能是速度單位或正負號抄錯，請核對投影片。")
        if summary["perigee_alt_km"] < 0:
            warnings.append(f"看起來{label}近地點高度 {summary['perigee_alt_km']:.3f} km 低於地表，可能是正負號或小數點抄錯，請核對投影片。")
    delta = abs((epochs["pursuer"] - epochs["evader"]).total_seconds()) if epochs["pursuer"] else 0
    alignment = "兩艘沒有填時間，工具會把這組數字當成同一時刻。"
    if epochs["pursuer"]:
        earlier = "追方" if epochs["pursuer"] < epochs["evader"] else "逃方"
        alignment = f"較早那艘（{earlier}）會先推 {delta:g} 秒對齊。" if delta else "兩艘時間相同，不用先推算對齊。"
    if delta > 86400:
        warnings.append(f"看起來兩艘時間差 {delta / 3600:.2f} 小時，可能是日期抄錯，請核對投影片。")
    if dv > 1000 or dv < 1:
        warnings.append(f"看起來 ΔV_lim 是 {dv:g} m/s，可能是 m/s 與 km/s 選錯，請核對投影片。")
    if window < 60 or window > 86400:
        warnings.append(f"看起來 T_round 是 {window:g} 秒，可能是秒、分鐘或小時選錯，請核對投影片。")
    if radius > 1000:
        warnings.append(f"看起來 R_cap 是 {radius:g} km，可能是公尺與公里選錯，請核對投影片。")
    rules = read_json(DRL / "configs" / "rulesets" / "final_official.json")
    rules.update(max_dv_pursuer_mps=dv, max_dv_evader_mps=dv, capture_radius_km=radius,
                 window_sec=window, safe_sma_km=bounds)
    readback = {"rules": rules, "ships": summaries, "epoch_delta_sec": delta, "alignment": alignment,
                "original": {key: value for key, value in body.items() if key not in ("confirm", "preview")}}
    result = {"valid": True, "readback": readback, "warnings": warnings,
              "needs_confirm": bool(warnings) and not body.get("confirm"), "saved": False}
    if body.get("preview") or result["needs_confirm"]:
        return result
    with MEDAL_LOCK:
        DAY.mkdir(parents=True, exist_ok=True)
        for name in ("announced.json", "initial.json", "announce_input.json", "role_select.json"):
            old = DAY / name
            if old.exists():
                shutil.copy2(old, DAY / f"{old.stem}.bak-{time.strftime('%H%M%S')}-{time.time_ns() % 1000000:06d}.json")
        write_json(DAY / "announced.json", rules)
        write_json(DAY / "initial.json", state)
        write_json(DAY / "announce_input.json", readback["original"])
        # 上一次選擇器的結果不屬於這次公告。
        (DAY / "role_select.json").unlink(missing_ok=True)
        write_json(DAY / "gui_readback.json", readback)
    result.update(saved=True, initial_version=str((DAY / "initial.json").stat().st_mtime_ns))
    return result


def usb_compare(body):
    initial, source = DAY / "initial.json", day_file(body.get("file"))
    if not initial.exists():
        raise UserError("還沒有手打初始狀態。請先在「抄公告與選角色」填好並存檔，再放 USB 檔。")
    if not source.is_file():
        raise UserError("找不到這份 USB 檔，請再拖放一次。")
    saved_input = read_json(DAY / "announce_input.json") if (DAY / "announce_input.json").exists() else {}
    names = medal_names(body) or medal_names(saved_input)
    values, dates, logs = {}, {}, {}
    # drl_state_to_json 對齊雙船後不保留 epoch；從同次解析的「共同 epoch」取回。
    with tempfile.TemporaryDirectory(prefix="gui-usb-", dir=DAY) as tmp:
        for label, path in (("manual", initial), ("usb", source)):
            target = Path(tmp) / f"{label}.json"
            cmd = DRLPY + [str(GUI_DIR / "drl_state_to_json.py"), str(path), str(target)]
            if names:
                cmd += ["--names", names]
            try:
                proc = subprocess.run(medal_epoch_command(cmd), cwd=DRL, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UserError(f"USB 比對工具沒有完成：{exc}。請核對金牌賽環境後再試。") from exc
            logs[label] = proc.stdout + proc.stderr
            if proc.returncode:
                raise UserError(f"{'手打資料' if label == 'manual' else 'USB 檔'}解析失敗，請核對船名與檔案：\n{logs[label]}")
            values[label] = read_json(target)
            match = re.search(r"^共同 epoch：(.+)$", proc.stdout, re.MULTILINE)
            dates[label] = epoch_utc(match.group(1)) if match else None
    present_dates = [val for val in dates.values() if val]
    common = max(present_dates) if present_dates else None
    time_known = (dates["manual"] is None) == (dates["usb"] is None)
    usb_state = json.loads(json.dumps(values["usb"]))
    for side, _ in SIDES:
        if dates["usb"]:
            usb_state[side]["epoch"] = utc_text(dates["usb"])
    for label in values:
        if common and dates[label]:
            dt = (common - dates[label]).total_seconds()
            for side, _ in SIDES:
                ship = values[label][side]
                try:
                    ship["r_km"], ship["v_kms"] = propagate(ship["r_km"], ship["v_kms"], dt)
                except (ValueError, OverflowError, ZeroDivisionError) as exc:
                    raise UserError(f"兩份檔案無法對齊時間：{exc}。請核對投影片與 USB 檔。") from exc
    rows = []
    for side, label in SIDES:
        for key, axes, tolerance, unit in (("r_km", ("X", "Y", "Z"), 0.001, "km"),
                                          ("v_kms", ("VX", "VY", "VZ"), 1e-6, "km/s")):
            for i, axis in enumerate(axes):
                manual, usb = values["manual"][side][key][i], values["usb"][side][key][i]
                diff = usb - manual
                rows.append({"side": side, "label": f"{label} {axis}", "unit": unit, "manual": manual,
                             "usb": usb, "diff": diff, "match": time_known and abs(diff) < tolerance})
        both = dates["manual"] is not None and dates["usb"] is not None
        diff = (dates["usb"] - dates["manual"]).total_seconds() if both else None
        rows.append({"side": side, "label": f"{label}對齊時間", "unit": "秒", "manual": utc_text(dates["manual"]),
                     "usb": utc_text(dates["usb"]), "diff": diff,
                     "match": abs(diff) < 1 if both else dates["manual"] == dates["usb"]})
    all_match = all(row["match"] for row in rows)
    adopted = False
    if body.get("adopt"):
        with MEDAL_LOCK:
            shutil.copy2(initial, DAY / f"initial.bak-{time.strftime('%H%M%S')}.json")
            write_json(initial, usb_state)
            (DAY / "gui_readback.json").unlink(missing_ok=True)
            (DAY / "role_select.json").unlink(missing_ok=True)
        adopted = True
    baseline = (f"各檔先把兩艘對齊到該檔較晚時間，再把位置與速度推到 {utc_text(common)} 比對。"
                "時間列核對各檔原本的對齊時間；USB 採用時保留 USB 自己的對齊時間。") if common else "兩份檔都沒有時間，直接比對位置與速度，請另向主辦核對時間。"
    if not time_known:
        baseline = "其中一份沒有時間，無法確認兩份位置與速度是同一時刻，先列為不一致。請向主辦核對時間；採用 USB 時保留 USB 自己的時間資料。"
    return {"rows": rows, "all_match": all_match, "baseline": baseline, "adopted": adopted,
            "message": "已改用 USB 檔，角色選擇器要重跑" if adopted else
                       "USB 檔跟手打的一致" if all_match else "USB 檔跟手打的不一樣，請核對紅色各列，再決定採用哪份。",
            "initial_version": str(initial.stat().st_mtime_ns), "output": logs}


def medal_submitted(body):
    with MEDAL_LOCK:
        if not (DAY / "session.json").exists():
            raise UserError("還沒有整場紀錄，請先選角色並建立。")
        session = read_json(DAY / "session.json")
        round_no = session.get("round")
        if session.get("finished") or body.get("round") != round_no:
            raise UserError("目前回合已經改變，請重新整理後核對回合再交出。")
        rec = next((row for row in session.get("rounds", []) if row.get("round") == round_no), {})
        expected = (rec.get("submission") or {}).get("line")
        if not expected or body.get("line") != expected:
            raise UserError("提交行和目前建議不一樣。請重新整理，照畫面最新的提交行核對後再按已交出。")
        entries = read_json(DAY / "submissions.json") if (DAY / "submissions.json").exists() else []
        existing = next((row for row in entries if row.get("round") == round_no), None)
        if existing:
            return {"submission": existing}
        estimated = body.get("remaining_sec") is None
        if estimated:
            advice_jobs = [job for job in list(JOBS.values()) if getattr(job, "medal_round", None) == round_no
                           and job.key == "medal.round.advise"]
            # 正常 GUI 一定帶 localStorage 算出的秒數；單獨呼叫 API 時以建議工作起點估算。
            remaining = 600 - (time.time() - advice_jobs[-1].started) if advice_jobs else 600.0
        else:
            remaining = num(body.get("remaining_sec"), "倒數剩餘秒數")
        entry = {"round": round_no, "line": expected, "local_time": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "remaining_sec": remaining, "remaining_estimated": estimated}
        entries.append(entry)
        write_json(DAY / "submissions.json", entries)
        return {"submission": entry}


def write_rules(body):
    tpl = read_json(DRL / "configs" / "rulesets" / "final_official.json")
    dvp, dve = num(body.get("dv_p"), "追方 ΔV_lim"), num(body.get("dv_e", body.get("dv_p")), "逃方 ΔV_lim")
    rcap, tround = num(body.get("rcap"), "R_cap"), num(body.get("tround"), "T_round")
    lo, hi = num(body.get("lo"), "安全空域下限"), num(body.get("hi"), "安全空域上限")
    if body.get("safe_unit") == "alt":
        lo, hi = lo + EARTH_R_KM, hi + EARTH_R_KM
    warn = []
    if not lo < hi:
        raise UserError("安全空域下限要小於上限")
    if lo < EARTH_R_KM:
        warn.append(f"安全空域下限 {lo:.1f} km 比地球半徑還小：題目給的可能是高度，單位要選「高度」")
    if dvp > 5000 or dve > 5000:
        warn.append("ΔV_lim 大於 5000：確認單位是 m/s，不是 km/s 的 1000 倍")
    if dvp < 1 or dve < 1:
        warn.append("ΔV_lim 小於 1：題目給的可能是 km/s，要乘 1000 換成 m/s")
    if tround < 60:
        warn.append("T_round 小於 60 秒：題目給的可能是分鐘，要換成秒")
    if rcap > 1000:
        warn.append("R_cap 大於 1000：確認單位是 km")
    tpl.update(max_dv_pursuer_mps=dvp, max_dv_evader_mps=dve, capture_radius_km=rcap, window_sec=tround,
               safe_sma_km=[lo, hi])
    write_json(DAY / "announced.json", tpl)
    return {"rules": read_rules(), "warnings": warn}


def read_rules():
    p = DAY / "announced.json"
    if not p.exists():
        return None
    r = read_json(p)
    return {k: r.get(k) for k in ("max_dv_pursuer_mps", "max_dv_evader_mps", "capture_radius_km", "window_sec",
                                  "safe_sma_km", "rounds")}


def write_manual_state(body):
    out = day_file(body.get("out") or "manual_state.json")
    state = {}
    for side, label in (("pursuer", "追方"), ("evader", "逃方")):
        vals = [num(body[side][k], f"{label} {k}") for k in ("X", "Y", "Z", "VX", "VY", "VZ")]
        if any(abs(v) > 100 for v in vals[3:]):
            raise UserError(f"{label} 速度超過 100：看起來是 m/s，要除以 1000 填 km/s")
        if any(abs(v) > 1e6 for v in vals[:3]):
            raise UserError(f"{label} 位置超過 1e6：看起來是公尺，要除以 1000 填 km")
        state[side] = {"r_km": vals[:3], "v_kms": vals[3:]}
    if out.exists() and not body.get("overwrite"):
        raise UserError(f"{out.name} 已經存在；換個檔名")
    write_json(out, state)
    return {"name": out.name}


def name_args(body):
    args = []
    if str(body.get("names") or "").strip():
        args += ["--names", body["names"].strip()]
    if str(body.get("order") or "").strip():
        args += ["--order", body["order"].strip()]
    return args


def medal_command(body):
    act = body.get("action")
    if act == "initial_parse":
        return "念回初始狀態", DRLPY + ["copilot.py", "final", "parse", f"{DAY_ARG}/initial.json"] + name_args(body)
    if act == "parse":
        # 跟 final parse 印一樣的摘要，另存成 JSON：role_select 只吃 JSON，USB 檔不一定是
        return "解析狀態檔", DRLPY + [str(GUI_DIR / "drl_state_to_json.py"), day_rel(body.get("file")),
                                     f"{DAY_ARG}/initial_state.json"] + name_args(body)
    if act == "convert":
        out = day_file(body.get("out") or "initial.json")
        return "經緯高轉檔", DRLPY + ["tools/gmat_state_convert.py", day_rel(body.get("file")), "--out",
                                    f"{DAY_ARG}/{out.name}", "--gmat-console", GMAT]
    if act == "role_select":
        if not (DAY / "announced.json").exists():
            raise UserError("先存規則檔")
        cmd = DRLPY + ["tools/role_select.py", day_rel(body.get("file")), "--rules", f"{DAY_ARG}/announced.json",
                       "--workers", "4", "--budget-sec", "150", "--json", f"{DAY_ARG}/role_select.json"]
        if body.get("fast"):
            cmd.append("--fast")
        return "角色選擇器", cmd
    if act == "new":
        role = body.get("role")
        if role not in ("pursuer", "evader"):
            raise UserError("角色要選追方或躲方")
        for job in list(JOBS.values()):
            if job.ended is None and job.key in ("medal.advise", "medal.announce", "medal.round.advise", "medal.round.announce", "medal.new", "medal.setup.new"):
                raise UserError("回合工作還在執行，請先在輸出框按停止，等它停止後再重建整場紀錄。")
        initial_arg = day_rel(body.get("file"))
        sess = DAY / "session.json"
        if sess.exists():
            if not body.get("overwrite"):
                raise UserError("day/session.json 已經存在。真的要重建就勾「覆蓋」，舊檔會備份")
            sess.rename(DAY / f"session.bak-{time.strftime('%H%M%S')}.json")
        if (DAY / "submissions.json").exists():
            shutil.copy2(DAY / "submissions.json", DAY / f"submissions.bak-{time.strftime('%H%M%S')}.json")
        write_json(DAY / "submissions.json", [])
        write_json(DAY / "gui_session.json", {"id": str(time.time_ns()), "names": body.get("names") or ""})
        return f"建 session（{'追方' if role == 'pursuer' else '躲方'}）", DRLPY + [
            "copilot.py", "final", "new", "--rules", f"{DAY_ARG}/announced.json", "--initial", initial_arg,
            "--role", role, "--out", f"{DAY_ARG}/session.json"] + name_args(body)
    if act == "advise":
        cmd = DRLPY + ["copilot.py", "final", "advise", f"{DAY_ARG}/session.json"]
        if body.get("file"):
            cmd += ["--state", day_rel(body["file"])]
        if body.get("fast"):
            cmd.append("--fast")
        return "本回合建議 advise", cmd
    if act == "announce":
        cmd = DRLPY + ["copilot.py", "final", "announce", f"{DAY_ARG}/session.json"]
        opp = body.get("opp") or []
        if not body.get("file") or any(str(v).strip() for v in opp):
            if len(opp) != 3 or any(not str(v).strip() for v in opp):
                raise UserError("只有 Δv 時要填 X、Y、Z 三個數；有狀態檔時可以全部留空。請補齊後再試。")
            cmd += ["--opponent-dv"] + [num_text(v, "對手 Δv") for v in opp]
        if any(str(v).strip() for v in body.get("our", [])):
            if len(body["our"]) != 3:
                raise UserError("我方 Δv 要填 X Y Z 三個數")
            cmd += ["--our-dv"] + [num_text(v, "我方 Δv") for v in body["our"]]
        if body.get("file"):
            cmd += ["--state", day_rel(body["file"])]
        if body.get("force"):
            cmd += ["--force"]
        return "核對回合結束狀態", cmd + name_args(body)
    if act == "show":
        return "整場摘要 show", DRLPY + ["copilot.py", "final", "show", f"{DAY_ARG}/session.json"]
    raise UserError(f"不認得的動作：{act}")


def parse_advise(text):
    out = {}
    for line in text.splitlines():
        s = line.strip()
        for key, prefix in (("submit", "提交："), ("recheck", "重驗："), ("cert", "安全證書："),
                            ("consistency", "一致性檢查："), ("after", "提交值推完："), ("handcheck", "手寫核對"),
                            ("head", "第 ")):
            if s.startswith(prefix) and key not in out:
                out[key] = s
    if "after" in out:
        m = re.search(r"a = ([-\d.]+)", out["after"])
        if m:
            out["a_after"] = float(m.group(1))
    # CLI 最後一行才是應交值；保留原有鍵，另記替代值與各軸供 GUI 恢復。
    for line in text.splitlines():
        if line.strip().startswith("提交："):
            out["submit"] = line.strip()
    out["used_alternative"] = bool(re.search(r"已找到通過重驗的替代|已換成替代|以下提交行使用替代", text))
    if out.get("submit"):
        pieces = out["submit"].split("：", 1)[-1].split(",")
        try:
            out["dv_mps"] = [float(val) for val in pieces[-3:]]
        except ValueError:
            pass
    return out


def set_medal_day(name):
    """切換金牌賽設定檔（一個資料夾，跟排位賽切設定檔同一套用法）。資料夾不用先存在，第一次寫檔時才建立。"""
    global DAY, DAY_ARG
    name = str(name).strip()
    if not NAME_RE.match(name):
        raise UserError("名稱只能用英文、數字、. _ -。")
    target = (DAY_BASE / name).resolve()
    if target != DAY:
        with JOBS_LOCK:
            busy = [j.title for j in JOBS.values() if j.key.startswith("medal.") and j.ended is None]
        if busy:
            raise UserError("金牌賽還有工作在跑（" + "、".join(busy) + "），等它跑完或按停止再切換。")
        DAY = target
        DAY_ARG = os.path.relpath(DAY, DRL) if DAY.is_relative_to(DRL) else str(DAY)
    return {"day_name": DAY.name, "day_path": str(DAY), "day_exists": DAY.exists()}


def medal_overview():
    sess, rounds, s, latest_announcement = None, [], {}, None
    p = DAY / "session.json"
    if p.exists():
        s = read_medal_session()
        for rec in s.get("rounds", []):
            sub, ann = rec.get("submission") or {}, rec.get("announcement") or {}
            rounds.append({"round": rec.get("round"), "line": sub.get("line"),
                           "passed": (sub.get("recheck") or {}).get("passed"),
                           "our_dv": sub.get("dv_mps"), "announced": bool(ann),
                           "opp_dv": ann.get("opponent_dv_mps"), "our_dv_ann": ann.get("our_dv_mps"),
                           "consistency": (rec.get("consistency") or {}).get("status"),
                           "announcement": ann, "round_result": rec.get("round_result")})
            if ann:
                actual, submitted = ann.get("our_dv_mps"), sub.get("dv_mps")
                difference = [a - b for a, b in zip(actual, submitted)] if actual is not None and submitted is not None else None
                latest_announcement = {"round": rec.get("round"), "source": ann.get("source"),
                                       "opponent_dv_mps": ann.get("opponent_dv_mps"), "our_dv_mps": actual,
                                       "typed_opponent_dv_mps": ann.get("typed_opponent_dv_mps"),
                                       "warnings": ann.get("warnings") or [], "dt_sec": ann.get("dt_sec"),
                                       "recovery": ann.get("recovery"), "our_difference_mps": difference,
                                       "our_matches_submission": max(map(abs, difference)) <= 0.05 if difference else None,
                                       "round_result": rec.get("round_result") or {}}
        sess = {"role": s.get("role"), "round": s.get("round"), "rounds_total": s.get("rules", {}).get("rounds"),
                "safe_sma_km": s.get("rules", {}).get("safe_sma_km"), "finished": s.get("finished"),
                "names": s.get("names"), "order": s.get("order")}
    rs = None
    if (DAY / "role_select.json").exists():
        try:
            rs = read_json(DAY / "role_select.json")
        except (OSError, ValueError):
            rs = None
    distance, evader_a, in_zone = None, None, None
    current = s.get("current_state") or {}
    try:
        distance = norm([a - b for a, b in zip(current["pursuer"]["r_km"], current["evader"]["r_km"])])
        evader_a = orbit_summary(current["evader"]["r_km"], current["evader"]["v_kms"])["sma_km"]
        bounds = s.get("rules", {}).get("safe_sma_km")
        in_zone = bounds[0] <= evader_a <= bounds[1] if bounds and evader_a is not None else None
    except (KeyError, TypeError, ValueError, OverflowError):
        pass
    submissions = read_json(DAY / "submissions.json") if (DAY / "submissions.json").exists() else []
    gui_session = read_json(DAY / "gui_session.json") if (DAY / "gui_session.json").exists() else {}
    session_id = None
    if sess:
        session_id = gui_session.get("id") or hashlib.sha256(json.dumps([s.get("initial"), s.get("role")], sort_keys=True).encode()).hexdigest()[:20]
    initial_version = str((DAY / "initial.json").stat().st_mtime_ns) if (DAY / "initial.json").exists() else None
    active = [{**job.info(), "medal_round": getattr(job, "medal_round", None),
               "medal_session_id": getattr(job, "medal_session_id", None)}
              for job in list(JOBS.values()) if job.key.startswith("medal.")]
    phase, advice = "setup", {}
    cur = next((rec for rec in s.get("rounds", []) if rec.get("round") == s.get("round")), {})
    logged = next((row for row in submissions if row.get("round") == s.get("round")), None)
    if sess:
        if s.get("finished") or s.get("round", 1) > (sess.get("rounds_total") or 6):
            phase = "E"
        elif logged and not cur.get("announcement"):
            phase = "D"
        elif cur.get("submission"):
            phase = "C"
        elif cur.get("announcement"):
            phase = "A"
        else:
            phase = "B"
        sub, agent = cur.get("submission") or {}, (cur.get("advice") or {}).get("agent_info") or {}
        if sub:
            recheck = sub.get("recheck") or {}
            advice = {"submit": "提交：" + sub.get("line", ""), "dv_mps": sub.get("dv_mps"),
                      "recheck": "重驗：" + ("通過" if recheck.get("passed") else "未通過"),
                      "cert": "安全證書：" + ("成立" if agent.get("certificate") else "未成立"),
                      "used_alternative": False}
            try:
                evader = (cur.get("start_state") or current)["evader"]
                velocity = [val + dv / 1000 for val, dv in zip(evader["v_kms"], sub["dv_mps"])] if s.get("role") == "evader" else evader["v_kms"]
                advice["a_after"] = orbit_summary(evader["r_km"], velocity)["sma_km"]
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        matching = [job for job in active if job["key"] == "medal.round.advise"
                    and job["medal_round"] == s.get("round") and job["medal_session_id"] in (None, session_id)]
        if matching:
            job = matching[-1]
            if job["running"]:
                phase = "B"
            elif job["rc"] == 0 and not logged:
                advice.update(parse_advise("\n".join(job["lines"])))
    readback = read_json(DAY / "gui_readback.json") if (DAY / "gui_readback.json").exists() else None
    return {"day_name": DAY.name, "day_default": DAY_DEFAULT, "day_path": str(DAY), "day_exists": DAY.exists(),
            "day_rel": os.path.relpath(DAY, ROOT) if DAY.is_relative_to(ROOT) else str(DAY),
            "day_choices": sorted(p.name for p in DAY_BASE.iterdir() if p.is_dir() and NAME_RE.match(p.name)
                                  and ((p / "announced.json").exists() or (p / "session.json").exists())),
            "rules": read_rules(), "files": medal_files(), "session": sess, "rounds": rounds,
            "role_select": rs, "drl": str(DRL), "drl_python": str(DRL_PYTHON), "drl_ok": DRL_PYTHON.exists(),
            "finished": s.get("finished"), "names": s.get("names"), "latest_announcement": latest_announcement,
            "distance_km": distance, "evader_sma_km": evader_a, "in_zone": in_zone, "submissions": submissions,
            "phase": phase, "advice": advice, "submitted": logged, "jobs": active,
            "session_id": session_id,
            "initial_version": initial_version, "readback": readback}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if method == "GET" and url.path in ("/", "/index.html"):
                return self.send(200, (GUI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            if method == "POST":
                if self.headers.get("Origin") not in (None, f"http://{self.headers.get('Host')}"):
                    raise UserError("拒絕外部網頁的請求")
            result = self.api(method, url.path, q)
            self.send(200, {"ok": True, **(result or {})})
        except UserError as exc:
            self.send(200, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 畫面要看得到錯誤，不要讓伺服器掛掉
            self.send(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def api(self, method, path, q):
        if path == "/api/jobs":
            return {"jobs": [j.info(len(j.lines)) for j in JOBS.values()]}
        if path == "/api/job":
            job = JOBS.get(q.get("id"))
            if job is None:
                raise UserError("找不到這個工作（GUI 重開過？）")
            return {"job": job.info(int(q.get("since", 0)))}
        if path == "/api/job/stop":
            stop_job(json.loads(self.body() or b"{}").get("id"))
            return {}
        if path == "/api/ranking/overview":
            return ranking_overview(q.get("name", "ranking"))
        if path == "/api/ranking/run":
            return {"summary": run_summary(check_name(q.get("run"), "執行目錄"))}
        if path == "/api/ranking/checklist":
            return {"checklist": checklist(check_name(q.get("rt")), q.get("name", "ranking"))}
        if path == "/api/ranking/config" and method == "POST":
            return {"config": save_ranking_config(json.loads(self.body()))}
        if path == "/api/ranking/variant" and method == "POST":
            return make_variant(json.loads(self.body()))
        if path == "/api/ranking/cmd" and method == "POST":
            body = json.loads(self.body())
            title, cmd = ranking_command(body)
            return {"job": start_job(body.get("key") or f"rank.{body.get('action')}", title, cmd, ROOT).info()}
        if path == "/api/volumes":
            vols = volumes()
            return {"volumes": list(vols), "paths": vols}
        if path == "/api/ranking/usb" and method == "POST":
            return save_to_usb(json.loads(self.body()))
        if path == "/api/reveal" and method == "POST":
            target = Path(json.loads(self.body()).get("path", ""))
            if target.exists():
                reveal(target)
            return {}
        if path == "/api/medal/overview":
            return medal_overview()
        if path == "/api/medal/day" and method == "POST":
            return set_medal_day(json.loads(self.body()).get("name", ""))
        if path == "/api/medal/announce_form" and method == "POST":
            return write_announce_form(json.loads(self.body()))
        if path == "/api/medal/usb_compare" and method == "POST":
            return usb_compare(json.loads(self.body()))
        if path == "/api/medal/submitted" and method == "POST":
            return medal_submitted(json.loads(self.body()))
        if path == "/api/medal/setup" and method == "POST":
            body = json.loads(self.body())
            if body.get("action") not in ("initial_parse", "role_select", "new"):
                raise UserError("這個開賽動作無法辨認，請回到「抄公告與選角色」重試。")
            keys = {"initial_parse": "medal.initial_parse", "role_select": "medal.setup.role_select", "new": "medal.setup.new"}
            DAY.mkdir(parents=True, exist_ok=True)
            with MEDAL_LOCK:
                title, cmd = medal_command(body)
                job = start_job(keys[body["action"]], title, medal_epoch_command(cmd), DRL)
            return {"job": job.info()}
        if path == "/api/medal/round" and method == "POST":
            body = json.loads(self.body())
            if body.get("action") not in ("advise", "announce", "show"):
                raise UserError("這個回合動作無法辨認，請重新整理後重試。")
            if not (DAY / "session.json").exists():
                raise UserError("還沒有整場紀錄，請先到「抄公告與選角色」選角色。")
            with MEDAL_LOCK:
                session = read_json(DAY / "session.json")
                if body.get("round") is not None and body["round"] != session.get("round"):
                    raise UserError("回合已經改變，請重新整理後再試。")
                if session.get("finished") and body["action"] != "show":
                    raise UserError(f"比賽已在第 {session['finished'].get('round')} 回合結束。請查看整場摘要，以主辦公告為準。")
                submitted = read_json(DAY / "submissions.json") if (DAY / "submissions.json").exists() else []
                if body["action"] == "advise" and any(row.get("round") == session.get("round") for row in submitted):
                    raise UserError("這回合已交出，請等主辦的回合結束狀態檔，再繼續下一回合。")
                for old in list(JOBS.values()):
                    if old.ended is None and old.key in ("medal.round.advise", "medal.round.announce"):
                        raise UserError("上一個回合工作還在跑，請等輸出完成後再試。")
                title, cmd = medal_command(body)
                job = start_job(f"medal.round.{body['action']}", title, medal_epoch_command(cmd), DRL)
                job.medal_round = session.get("round")
                meta = read_json(DAY / "gui_session.json") if (DAY / "gui_session.json").exists() else {}
                job.medal_session_id = meta.get("id")
            return {"job": job.info()}
        if path == "/api/medal/rules" and method == "POST":
            return write_rules(json.loads(self.body()))
        if path == "/api/medal/manual" and method == "POST":
            return write_manual_state(json.loads(self.body()))
        if path == "/api/medal/upload" and method == "POST":
            if self.headers.get("X-ODC-Upload") != "1":
                raise UserError("拒絕外部網頁的上傳")
            dest = day_file(q.get("name"))
            DAY.mkdir(parents=True, exist_ok=True)
            if dest.exists() and q.get("overwrite") != "1":
                stem, suf = os.path.splitext(dest.name)
                dest = DAY / f"{stem}-{time.strftime('%H%M%S')}{suf}"
            dest.write_bytes(self.body())
            return {"name": dest.name}
        if path == "/api/medal/file":
            p = day_file(q.get("name"))
            return {"name": p.name, "text": p.read_text(encoding="utf-8", errors="replace")[:20000]}
        if path == "/api/medal/cmd" and method == "POST":
            body = json.loads(self.body())
            DAY.mkdir(parents=True, exist_ok=True)
            title, cmd = medal_command(body)
            return {"job": start_job(body.get("key") or f"medal.{body.get('action')}", title, cmd, DRL).info()}
        if path == "/api/medal/advise":
            return {"advise": parse_advise(job_output(q.get("id")))}
        raise UserError(f"沒有這個 API：{method} {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"ODC 決賽 GUI：{url}\n排位賽資料夾 {ROOT}\n金牌賽資料夾 {DRL}\n"
          f"GMAT：{GMAT}（{GMAT_SOURCE or '找不到，執行 setup.sh 或在 configs/local/config.json 填 local.gmat_console_path'}）\n"
          "關掉這個視窗或按 Ctrl+C 結束。", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for job in list(JOBS.values()):
            stop_job(job.id)


if __name__ == "__main__":
    sys.exit(main())
