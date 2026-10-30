"""計分參數 k_t、C_t、k_v、C_v 的單位換算與驗算。

為什麼要有這個（docs/archive/prelim/CONTEST_DAY.md「單位陷阱」）：初賽官方給 kv = 1.1862 (km/s)^-1、
Cv = 2.955723 km/s，工具的 Δv 一律用 m/s，照抄會讓燃料項整個算錯。排位賽的參數比賽當下才
公布，現場要在幾分鐘內換對。

工具單位：k_t [1/s]、C_t [s]、k_v [1/(m/s)]、C_v [m/s]。

三種驗算：
  1. 參考解的分數：主辦單位初賽是照參考解校準參數的，參考解剛好 50 + 22.50 + 17.50 = 90.00。
     官方若給參考解，換對單位的話總分（甚至各分項）應該落在整數或 0.5 的倍數附近。
     `unit_hypotheses` 把 k_v/C_v 的每一種單位解讀都算一次，只有換對的那組會落在整數上。
  2. 無單位乘積 k_v·C_v、k_t·C_t：單位一致地換算時乘積不變（初賽 3.506、14.99）。只換了
     其中一個，乘積會差 1000 倍（或 60、3600 倍），燃料項在 Δv=0 時就拿不到 12.5 分以上。
  3. 數值範圍：C_v 在 m/s 制下應該是幾百到幾千；C_v < 50 幾乎一定還是 km/s。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# 各單位換成工具單位要乘的係數
_KT_UNITS = {"1/s": 1.0, "1/min": 1.0 / 60.0, "1/h": 1.0 / 3600.0}
_CT_UNITS = {"s": 1.0, "min": 60.0, "h": 3600.0}
_KV_UNITS = {"1/(m/s)": 1.0, "1/(km/s)": 1.0 / 1000.0}
_CV_UNITS = {"m/s": 1.0, "km/s": 1000.0}
_DV_UNITS = _CV_UNITS
_T_UNITS = _CT_UNITS

_ALIASES = {
    # 反時間
    "s^-1": "1/s", "/s": "1/s", "1/sec": "1/s", "sec^-1": "1/s",
    "min^-1": "1/min", "/min": "1/min",
    "h^-1": "1/h", "/h": "1/h", "1/hr": "1/h", "hr^-1": "1/h",
    # 時間
    "sec": "s", "second": "s", "seconds": "s", "秒": "s",
    "minute": "min", "minutes": "min", "分": "min",
    "hr": "h", "hour": "h", "hours": "h", "小時": "h",
    # 反速度
    "(m/s)^-1": "1/(m/s)", "s/m": "1/(m/s)", "1/mps": "1/(m/s)", "1/m/s": "1/(m/s)",
    "(km/s)^-1": "1/(km/s)", "s/km": "1/(km/s)", "1/kmps": "1/(km/s)", "1/km/s": "1/(km/s)",
    # 速度
    "mps": "m/s", "kmps": "km/s",
}


class UnitError(ValueError):
    pass


def _norm_unit(u: str, table: dict, what: str) -> str:
    key = str(u).strip().lower().replace(" ", "").replace("⁻¹", "^-1")
    key = _ALIASES.get(key, key)
    if key not in table:
        raise UnitError(f"{what} 的單位 {u!r} 看不懂；可用：{', '.join(table)}")
    return key


@dataclass
class ToolParams:
    k_t: float   # 1/s
    C_t: float   # s
    k_v: float   # 1/(m/s)
    C_v: float   # m/s

    def as_rules(self) -> dict:
        return {"k_t": self.k_t, "C_t": self.C_t, "k_v": self.k_v, "C_v": self.C_v}


def convert(k_t, k_t_unit, C_t, C_t_unit, k_v, k_v_unit, C_v, C_v_unit) -> ToolParams:
    """官方參數 + 單位 → 工具單位。"""
    return ToolParams(
        k_t=_clean(float(k_t) * _KT_UNITS[_norm_unit(k_t_unit, _KT_UNITS, "k_t")]),
        C_t=_clean(float(C_t) * _CT_UNITS[_norm_unit(C_t_unit, _CT_UNITS, "C_t")]),
        k_v=_clean(float(k_v) * _KV_UNITS[_norm_unit(k_v_unit, _KV_UNITS, "k_v")]),
        C_v=_clean(float(C_v) * _CV_UNITS[_norm_unit(C_v_unit, _CV_UNITS, "C_v")]),
    )


def _clean(x: float) -> float:
    """1.1862 / 1000 = 0.0011861999999999999 這種浮點尾巴去掉（留 12 位有效數字），寫進 config 才好核對。"""
    return float(f"{x:.12g}")


def to_mps(dv, unit) -> float:
    return _clean(float(dv) * _DV_UNITS[_norm_unit(unit, _DV_UNITS, "Δv")])


def to_sec(t, unit) -> float:
    return _clean(float(t) * _T_UNITS[_norm_unit(unit, _T_UNITS, "時間")])


def _sigmoid25(x: float) -> float:
    return 25.0 / (1.0 + math.exp(min(x, 700.0)))


@dataclass
class ScoreTerms:
    dist: float
    time: float
    fuel: float
    penalty: float

    @property
    def total(self) -> float:
        return max(self.dist + self.time + self.fuel - self.penalty, 0.0)


def score_terms(p: ToolParams, dmin_km: float, t_sec: float, dv_mps: float,
                penalty_count: int = 0) -> ScoreTerms:
    """規則的計分公式拆成分項，跟 src.scorer.calculate_score 相同。"""
    dr = max(float(dmin_km), 5.0)
    return ScoreTerms(dist=50.0 * math.exp(-(dr - 5.0) / 100.0),
                      time=_sigmoid25(p.k_t * (float(t_sec) - p.C_t)),
                      fuel=_sigmoid25(p.k_v * (float(dv_mps) - p.C_v)),
                      penalty=10.0 * int(penalty_count))


def nearest_grid(x: float, step: float) -> tuple[float, float]:
    """x 最接近的 step 倍數，以及差多少。"""
    g = round(x / step) * step
    return g, x - g


_SATURATION = 0.01


def saturated(term: float) -> bool:
    """sigmoid 項貼在 0 或 25：參考解落在這裡代表參數幾乎一定換錯（主辦不會這樣校準）。"""
    return term < _SATURATION or term > 25.0 - _SATURATION


def looks_calibrated(terms: ScoreTerms, tol: float = 0.01) -> bool:
    """總分落在整數 ±tol 內，而且時間、燃料項都沒有飽和。

    初賽參考解是 90.00（分項 50 / 22.50 / 17.50）。飽和的項（0 或 25）會讓錯的單位也湊出
    整數（例如 50 + 25 + 25 = 100），所以一起排除。
    """
    if saturated(terms.time) or saturated(terms.fuel):
        return False
    return abs(nearest_grid(terms.total, 1.0)[1]) <= tol


@dataclass
class Hypothesis:
    label: str
    params: ToolParams
    terms: ScoreTerms
    calibrated: bool


def unit_hypotheses(k_t, C_t, k_v_raw, C_v_raw, ref_dmin_km, ref_t_sec, ref_dv_mps,
                    tol: float = 0.01) -> list[Hypothesis]:
    """k_v、C_v 的四種單位解讀各算一次參考解的分數（k_t/C_t 已換成 1/s、s）。

    用途：官方沒寫清楚單位、或懷疑抄錯時，看哪一種解讀讓參考解落在整數分。
    """
    out = []
    for kv_u in _KV_UNITS:
        for cv_u in _CV_UNITS:
            p = ToolParams(k_t=float(k_t), C_t=float(C_t),
                           k_v=float(k_v_raw) * _KV_UNITS[kv_u], C_v=float(C_v_raw) * _CV_UNITS[cv_u])
            t = score_terms(p, ref_dmin_km, ref_t_sec, ref_dv_mps)
            out.append(Hypothesis(f"k_v 當 {kv_u}、C_v 當 {cv_u}", p, t, looks_calibrated(t, tol)))
    return out


def sanity_warnings(p: ToolParams, t_max_sec: float | None = None,
                    max_total_dv_mps: float | None = 3000.0) -> list[str]:
    """不需要參考解的檢查：數量級與無單位乘積。回傳警告字串（空 = 沒看到異常）。"""
    w = []
    if p.C_v < 50.0:
        w.append(f"C_v = {p.C_v:g} m/s 太小，幾乎一定還是 km/s（要 ×1000）")
    if p.k_v > 0.1:
        w.append(f"k_v = {p.k_v:g} 1/(m/s) 太大（100 m/s 就讓燃料項掉光），可能還是 1/(km/s)（要 ÷1000）")
    kv_cv = p.k_v * p.C_v
    if not (0.3 <= kv_cv <= 100.0):
        w.append(f"k_v·C_v = {kv_cv:.4g}（無單位，初賽是 3.506）不在 0.3–100：k_v 和 C_v 可能只換了一個，"
                 f"Δv=0 時燃料項只有 {_sigmoid25(-kv_cv):.2f} 分")
    kt_ct = p.k_t * p.C_t
    if not (0.3 <= kt_ct <= 1000.0):
        w.append(f"k_t·C_t = {kt_ct:.4g}（無單位，初賽是 14.99）不在 0.3–1000：k_t 和 C_t 的時間單位可能不一致")
    if p.k_t <= 0.0 or p.k_v <= 0.0:
        w.append("k_t、k_v 應該是正數（越晚、越耗油分數越低）")
    if t_max_sec is not None and t_max_sec > 0.0 and p.C_t > t_max_sec:
        w.append(f"C_t = {p.C_t:g} s 比 T_max = {t_max_sec:g} s 還晚：時間項在整個可行窗內都 ≥ 12.5 分，"
                 "確認 C_t 的單位（分鐘？小時？）")
    if max_total_dv_mps is not None and p.C_v > 2.0 * max_total_dv_mps:
        w.append(f"C_v = {p.C_v:g} m/s 遠大於總 Δv 上限 {max_total_dv_mps:g} m/s：燃料項在合法範圍內幾乎不動，"
                 "確認單位")
    return w


# 初賽範例題目（rules/軌道設計競賽_參賽選手注意事項_20260828.pdf §八與 2026-08-28 來信）
PRELIM_OFFICIAL = dict(k_t=0.003982, k_t_unit="1/s", C_t=3763.526, C_t_unit="s",
                       k_v=1.1862, k_v_unit="1/(km/s)", C_v=2.955723, C_v_unit="km/s")
PRELIM_REF = dict(dmin_km=5.0, t_sec=3211.737, dv_mps=2241.427)
