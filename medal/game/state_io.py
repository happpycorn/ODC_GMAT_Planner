"""讀外部狀態來源（GMAT ReportFile）→ copilot 局勢檔欄位（HAP-109）。

當天每回合手抄六根數又慢又容易抄錯（初賽踩過 k_v 單位陷阱），所以這裡：
  * 讀 GMAT ReportFile（WriteHeaders=true 時用表頭欄名對應；沒表頭時可給 columns）
  * 支援笛卡兒（X Y Z VX VY VZ，EarthMJ2000Eq）與六根數（SMA ECC INC RAAN AOP TA）
  * 自動辨識哪艘是追者/躲者（依 spacecraft 名稱參數）
  * 數值合理性防呆：位置像公尺、速度像 m/s、高度不合理 → 直接報錯，不默默吞下

GMAT 表頭長這樣（Report 指令輸出的參數名，空白分隔）：
    ShipP.ElapsedSecs  ShipP.EarthMJ2000Eq.X ... ShipE.EarthMJ2000Eq.VZ
六根數：ShipP.Earth.SMA ShipP.Earth.ECC ShipP.EarthMJ2000Eq.INC ...（GMAT 會帶中心天體/座標系前綴）
"""
import math

import numpy as np

from physics import RE_VAL

CART = ("X", "Y", "Z", "VX", "VY", "VZ")
KEP = ("SMA", "ECC", "INC", "RAAN", "AOP", "TA")


class StateImportError(ValueError):
    pass


def read_gmat_report(path, columns=None, row=-1):
    """回傳 {欄名: 值} dict（取第 row 列，預設最後一列）。"""
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines:
        raise StateImportError(f"報表是空的：{path}")
    first = lines[0].split()
    has_header = any(not _is_number(tok) for tok in first)
    if has_header:
        header, data = first, lines[1:]
    else:
        if not columns:
            raise StateImportError("報表沒有表頭，請用 columns 指定欄名（例：ShipP.ElapsedSecs ShipP.EarthMJ2000Eq.X ...）")
        header, data = list(columns), lines
    if not data:
        raise StateImportError("報表只有表頭沒有資料列")
    vals = data[row].split()
    if len(vals) != len(header):
        raise StateImportError(f"欄數不符：表頭 {len(header)} 欄、資料 {len(vals)} 欄")
    return {h: float(v) for h, v in zip(header, vals)}


def _is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def _field(rec, ship, key):
    """找 ship 開頭、以 .key 結尾的欄位（容忍中間的座標系/天體前綴）。"""
    hits = [k for k in rec if k.split(".")[0] == ship and k.split(".")[-1] == key]
    if len(hits) > 1:
        raise StateImportError(f"{ship} 的 {key} 對到多個欄位：{hits}")
    return rec[hits[0]] if hits else None


def ship_entry(rec, ship):
    """把某艘船的欄位轉成局勢檔 entry（elements 或 r_km/v_kms），並做合理性檢查。"""
    cart = [_field(rec, ship, k) for k in CART]
    kep = [_field(rec, ship, k) for k in KEP]
    if all(v is not None for v in cart):
        r, v = np.array(cart[:3]), np.array(cart[3:])
        rn, vn = float(np.linalg.norm(r)), float(np.linalg.norm(v))
        if rn > 1e6:
            raise StateImportError(f"{ship} 位置 |r|={rn:.3g}：看起來是公尺，GMAT EarthMJ2000Eq 應該是 km")
        if vn > 100:
            raise StateImportError(f"{ship} 速度 |v|={vn:.3g}：看起來是 m/s，應該是 km/s")
        if not (RE_VAL - 50 < rn < 500000):
            raise StateImportError(f"{ship} 距地心 {rn:.1f} km 不合理（地表 {RE_VAL} km）")
        if not (0.1 < vn < 15):
            raise StateImportError(f"{ship} 速度 {vn:.3f} km/s 不合理")
        return {"r_km": r.tolist(), "v_kms": v.tolist()}
    if all(x is not None for x in kep):
        el = dict(zip(("sma", "ecc", "inc", "raan", "aop", "ta"), kep))
        if abs(el["sma"]) > 1e6:
            raise StateImportError(f"{ship} SMA={el['sma']:.3g}：看起來是公尺")
        if max(abs(el["inc"]), abs(el["raan"]), abs(el["aop"]), abs(el["ta"])) <= 2 * math.pi + 1e-9 and \
                any(abs(el[k]) > 1e-6 for k in ("inc", "raan", "aop", "ta")):
            raise StateImportError(f"{ship} 角度全部 <= 2π：可能是弧度，GMAT 六根數角度單位是度（確認後再匯入）")
        if el["ecc"] > 1.0:
            # 雙曲線（排位賽的飛掠船）：GMAT 慣例 SMA < 0，近地點半徑 = SMA·(1 − ECC)，真近點角要在漸近線內
            if not el["sma"] < 0.0:
                raise StateImportError(f"{ship} ECC={el['ecc']} > 1 是雙曲線，SMA 應該是負的（GMAT 慣例），收到 {el['sma']}")
            if el["sma"] * (1.0 - el["ecc"]) < RE_VAL - 50:
                raise StateImportError(f"{ship} 雙曲線近地點半徑 {el['sma'] * (1.0 - el['ecc']):.1f} km 在地表下，不合理")
            if 1.0 + el["ecc"] * math.cos(math.radians(el["ta"])) <= 0.0:
                raise StateImportError(f"{ship} TA={el['ta']}° 在雙曲線漸近線外（|TA| 要 < "
                                       f"{math.degrees(math.acos(-1.0 / el['ecc'])):.2f}°）")
        elif not (0.0 <= el["ecc"] < 1.0 and el["sma"] > RE_VAL):
            raise StateImportError(f"{ship} 六根數不合理（sma={el['sma']}, ecc={el['ecc']}）")
        return {"elements": el}
    missing = [k for k, v in zip(CART, cart) if v is None]
    raise StateImportError(f"報表裡找不到 {ship} 的完整狀態（笛卡兒缺 {missing}，六根數也不完整）。"
                           f"可用欄位：{sorted(rec)}")


def apply_report_to_state(st, rec, pursuer_ship, evader_ship, t_offset=0.0):
    """用報表紀錄更新局勢檔（就地修改並回傳）。"""
    st = dict(st)
    st["pursuer"] = ship_entry(rec, pursuer_ship)
    st["evader"] = ship_entry(rec, evader_ship)
    t = _field(rec, pursuer_ship, "ElapsedSecs")
    if t is None:
        t = _field(rec, evader_ship, "ElapsedSecs")
    if t is not None:
        st["t_elapsed_sec"] = float(t) + t_offset
    return st
