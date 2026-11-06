"""金／銅牌賽的官方狀態檔匯入（EarthMJ2000Eq，km、km/s）。

主辦的 USB 檔格式尚未公布；先辨識格式並保留判斷依據，讓隊員能核對原始檔。
所有入口都回傳雙方 (r, v)、epoch、經過秒數、格式與匯入備註。
"""
import csv
import json
import math
import re

import numpy as np

from game.initial_state import parse_epoch
from game.state_io import CART, KEP, StateImportError, _field, ship_entry
from physics import RE_VAL, get_r0_v0


DEFAULT_NAMES = {
    "pursuer": ("pursuer", "chaser", "shipp", "p", "追方", "追擊", "攔截"),
    "evader": ("evader", "target", "shipe", "e", "逃方", "躲方", "目標"),
}
_SIDES = ("pursuer", "evader")
_NAME_FIELDS = {"name", "ship", "side", "role", "角色", "衛星"}
_TIME_FIELDS = {"epoch", "time", "utcg​​regorian", "utcgregorian", "elapsedsecs", "tsec"}


def _number(value, line, column):
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise StateImportError(f"第 {line} 列第 {column} 欄 {value!r} 不是數字；請檢查小數點、逗號與欄位順序") from exc
    if not math.isfinite(x):
        raise StateImportError(f"第 {line} 列第 {column} 欄 {value!r} 不是有限數字；請換成實際數值")
    return x


def _epoch(value, line, column):
    try:
        return parse_epoch(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise StateImportError(f"第 {line} 列第 {column} 欄的時間 {value!r} 無法解析：{exc}") from exc


def _alias_map(names):
    aliases = {side: list(values) for side, values in DEFAULT_NAMES.items()}
    if names is None:
        return aliases
    if isinstance(names, str):
        value = names.strip()
        if value.startswith("{"):
            try:
                names = json.loads(value)
            except json.JSONDecodeError as exc:
                raise StateImportError(f"--names 不是合法 JSON：{exc}；請用追方／逃方的名稱對照") from exc
        elif "=" in value or ":" in value:
            chunks = re.split(r",(?=\s*(?:pursuer|evader)\s*[:=])", value, flags=re.I)
            names = {}
            for chunk in chunks:
                side, sep, item = chunk.partition("=")
                if not sep:
                    side, sep, item = chunk.partition(":")
                names[side.strip().lower()] = [x.strip() for x in item.split("|") if x.strip()]
        else:
            names = [x.strip() for x in value.split(",")]
    if isinstance(names, (tuple, list)) and len(names) == 2:
        names = dict(zip(_SIDES, names))
    if not isinstance(names, dict) or any(side not in _SIDES for side in names):
        raise StateImportError("--names 請用 pursuer=船名,evader=船名，或 JSON 物件指定兩方名稱")
    for side, values in names.items():
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple)) or not values or not all(isinstance(x, str) and x.strip() for x in values):
            raise StateImportError(f"--names 的 {side} 名稱須為非空文字或文字清單")
        aliases[side] = [x.strip().casefold() for x in values]
    return aliases


def _order(order):
    if order is None:
        return None
    if isinstance(order, str):
        order = [x.strip().casefold() for x in order.split(",")]
    if not isinstance(order, (tuple, list)) or len(order) != 2 or set(order) != set(_SIDES):
        raise StateImportError("--order 請寫 pursuer,evader 或 evader,pursuer，表示檔案前後順序")
    return tuple(order)


def _match_name(name, aliases):
    if name is None:
        return None
    word = str(name).strip().casefold()
    matches = []
    for side, values in aliases.items():
        for alias in values:
            alias = alias.casefold()
            if word == alias:
                matches.append((2, len(alias), side))
            elif len(alias) > 1 and alias in word:
                matches.append((1, len(alias), side))
    if not matches:
        return None
    best = max((rank, length) for rank, length, _ in matches)
    sides = {side for rank, length, side in matches if (rank, length) == best}
    return next(iter(sides)) if len(sides) == 1 else None


def _resolve_names(seen, names, order, *, unlabeled=False):
    aliases = _alias_map(names)
    sequence = _order(order)
    if len(seen) != 2:
        raise StateImportError(f"應有兩艘的狀態，實際看到 {len(seen)} 個名稱 {seen!r}；請檢查檔案資料列")
    recognized = [_match_name(name, aliases) for name in seen]
    if sequence is not None:
        for i, side in enumerate(recognized):
            if side is not None and side != sequence[i]:
                raise StateImportError(f"追方／逃方可能對調：第 {i + 1} 艘 {seen[i]!r} 看起來是 {side}，"
                                       f"但 --order 指成 {sequence[i]}；請核對船名或移除錯誤的 --order")
    if recognized == ["pursuer", "evader"] or recognized == ["evader", "pursuer"]:
        return {side: i for i, side in enumerate(recognized)}, ["依檔案船名辨識追方與逃方。"]
    if sequence is not None:
        return {side: i for i, side in enumerate(sequence)}, ["名稱無法完整辨識；依 --order 指定前後順序。"]
    if unlabeled and seen == [None, None]:
        return {"pursuer": 0, "evader": 1}, ["資料沒有船名；假設前六個數字是追方、後六個是逃方。"]
    raise StateImportError(f"無法判斷追方與逃方；檔案裡看到的名稱：{seen!r}。"
                           "請用 --names pursuer=船名,evader=船名，或 --order pursuer,evader 指定順序")


def _validate_ship(side, state):
    r, v = state
    if r.shape != (3,) or v.shape != (3,) or not (np.isfinite(r).all() and np.isfinite(v).all()):
        raise StateImportError(f"{side} 須有 3 個有限位置與 3 個有限速度數字；請檢查 X Y Z VX VY VZ")
    rn, vn = float(np.linalg.norm(r)), float(np.linalg.norm(v))
    if rn > 1e6:
        raise StateImportError(f"{side} 位置 |r|={rn:.3g} 看起來是公尺；請先除以 1000，填 km")
    if vn > 100:
        raise StateImportError(f"{side} 速度 |v|={vn:.3g} 看起來是 m/s；請先除以 1000，填 km/s")
    if rn < RE_VAL:
        raise StateImportError(f"{side} 距地心 {rn:.3f} km，在地表下（地球半徑 {RE_VAL} km）；請核對座標系與單位")
    if rn > 500000:
        raise StateImportError(f"{side} 距地心 {rn:.3f} km 不合理；請核對 km 單位與座標系")
    if not 0.1 < vn < 15:
        raise StateImportError(f"{side} 速度 {vn:.3f} km/s 不合理；請核對 km/s 單位與速度欄位")


def _finish(states, epochs, t_sec, fmt, notes):
    for side in _SIDES:
        if side not in states:
            raise StateImportError(f"缺 {side} 的狀態；請提供雙方各六個 X Y Z VX VY VZ 數字")
        _validate_ship(side, states[side])
    rp, vp = states["pursuer"]
    re, ve = states["evader"]
    if float(np.linalg.norm(rp - re)) < 1e-6 and float(np.linalg.norm(vp - ve)) < 1e-9:
        raise StateImportError("追方與逃方的六個數字一樣；可能複製了同一艘，請回原檔核對兩艘狀態")
    known = {side: value for side, value in epochs.items() if value is not None}
    common = next(iter(known.values())) if len(set(known.values())) == 1 and known else None
    result = {"pursuer": states["pursuer"], "evader": states["evader"],
              "epoch": common, "t_sec": t_sec, "format": fmt, "notes": list(notes)}
    if known:
        result["ship_epochs"] = dict(known)
        if len(set(known.values())) > 1:
            result["notes"].append("兩艘 epoch 不同；初始回合請先用 align_initial_states 對齊。")
    return result


def _six(values, line, first_column=1):
    if len(values) != 6:
        raise StateImportError(f"第 {line} 列應有 6 個數字（X Y Z VX VY VZ），實際有 {len(values)} 欄；請檢查缺欄或多欄")
    nums = [_number(value, line, first_column + i) for i, value in enumerate(values)]
    return np.asarray(nums[:3], dtype=float), np.asarray(nums[3:], dtype=float)


def _json_state(value, side, line):
    epoch = None
    if isinstance(value, list):
        return _six(value, line), epoch
    if not isinstance(value, dict):
        raise StateImportError(f"JSON 的 {side} 應是六個數字的清單，或含 r_km、v_kms 的物件")
    if value.get("epoch") is not None:
        epoch = _epoch(value["epoch"], line, "epoch")
    if "elements" in value:
        elements = value["elements"]
        if not isinstance(elements, dict):
            raise StateImportError(f"JSON 的 {side}.elements 應是 SMA ECC INC RAAN AOP TA 六根數物件")
        numeric = {}
        for i, (key, val) in enumerate(elements.items(), 1):
            numeric[f"{side}.{str(key).upper()}"] = _number(val, line, i)
        entry = ship_entry(numeric, side)
        if "elements" not in entry:
            raise StateImportError(f"JSON 的 {side}.elements 缺六根數欄位；請給 SMA ECC INC RAAN AOP TA")
        try:
            r, v = get_r0_v0(**entry["elements"])
        except (ValueError, TypeError, OverflowError) as exc:
            raise StateImportError(f"JSON 的 {side}.elements 無法轉成位置速度：{exc}") from exc
        return (np.asarray(r, dtype=float), np.asarray(v, dtype=float)), epoch
    if "r_km" not in value or "v_kms" not in value:
        raise StateImportError(f"JSON 的 {side} 缺 r_km 或 v_kms；兩者都要有，單位是 km 與 km/s")
    r, v = value["r_km"], value["v_kms"]
    if not isinstance(r, (list, tuple)) or not isinstance(v, (list, tuple)) or len(r) != 3 or len(v) != 3:
        raise StateImportError(f"JSON 的 {side}.r_km 與 v_kms 都須各有 3 個數字；請檢查缺欄或多欄")
    return _six([*r, *v], line), epoch


def _read_json(content, notes, names, order):
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise StateImportError(f"JSON 第 {exc.lineno} 列第 {exc.colno} 欄格式錯誤：{exc.msg}；請檢查逗號與引號") from exc
    if not isinstance(data, dict):
        raise StateImportError("JSON 最外層須是物件，含 pursuer 與 evader；請檢查大括號")
    keys = [key for key in data if key not in ("epoch", "t_sec", "t_elapsed_sec")]
    mapping, extra = _resolve_names(keys, names, order)
    states, epochs = {}, {}
    for side, index in mapping.items():
        states[side], epochs[side] = _json_state(data[keys[index]], side, index + 1)
    if data.get("epoch") is not None:
        common = _epoch(data["epoch"], 1, "epoch")
        for side in _SIDES:
            epochs.setdefault(side, common)
            if epochs[side] is None:
                epochs[side] = common
    t_sec = data.get("t_sec", data.get("t_elapsed_sec"))
    if t_sec is not None:
        t_sec = _number(t_sec, 1, "t_sec")
    return _finish(states, epochs, t_sec, "json", notes + extra)


def _normalized_gmat_key(key):
    parts = key.split(".")
    tail = parts[-1].casefold()
    names = {name.casefold(): name for name in (*CART, *KEP)}
    names.update({"elapsedsecs": "ElapsedSecs", "utcgregorian": "UTCGregorian"})
    if len(parts) < 2 or tail not in names:
        return key
    return ".".join([*parts[:-1], names[tail]])


def _gmat_row(header, raw, line):
    tokens = raw.split()
    record = {}
    index = 0
    for column, original in enumerate(header, 1):
        key = _normalized_gmat_key(original)
        n = 4 if key.endswith(".UTCGregorian") else 1
        if index + n > len(tokens):
            raise StateImportError(f"GMAT 第 {line} 列第 {column} 欄缺資料；表頭有 {len(header)} 欄，"
                                   "UTCGregorian 日期會佔四個空白分隔字；請檢查缺欄")
        value = " ".join(tokens[index:index + n]) if n == 4 else tokens[index]
        if key in record:
            raise StateImportError(f"GMAT 表頭 {key!r} 重複；請刪除重複欄位")
        record[key] = _epoch(value, line, column) if n == 4 else _number(value, line, column)
        index += n
    if index != len(tokens):
        raise StateImportError(f"GMAT 第 {line} 列多出 {len(tokens) - index} 個值；請核對表頭與 UTCGregorian 欄位")
    return record


def _read_gmat(lines, notes, names, order):
    first_line, first = lines[0]
    header = first.split()
    has_header = any("." in cell and not _looks_number(cell) for cell in header)
    if not has_header:
        sequence = _order(order)
        if sequence is None:
            raise StateImportError("GMAT 報表沒有表頭；請加 --order pursuer,evader，並確認每列依序是兩艘的 X Y Z VX VY VZ")
        line, raw = lines[-1]
        values = raw.split()
        if len(values) != 12:
            raise StateImportError(f"無表頭 GMAT 第 {line} 列應有 12 個數字，實際有 {len(values)}；請檢查缺欄或多欄")
        states = {sequence[0]: _six(values[:6], line), sequence[1]: _six(values[6:], line, 7)}
        return _finish(states, {}, None, "gmat", notes + ["無表頭 GMAT：依 --order 指定的順序讀最後一列。"])
    if len(lines) < 2:
        raise StateImportError("GMAT 報表只有表頭、沒有資料列；請重新輸出狀態")
    line, raw = lines[-1]
    record = _gmat_row(header, raw, line)
    seen = list(dict.fromkeys(key.split(".")[0] for key in record if "." in key))
    mapping, extra = _resolve_names(seen, names, order)
    states, epochs = {}, {}
    for side, index in mapping.items():
        ship = seen[index]
        entry = ship_entry(record, ship)
        if "elements" in entry:
            try:
                r, v = get_r0_v0(**entry["elements"])
            except (ValueError, TypeError, OverflowError) as exc:
                raise StateImportError(f"GMAT {ship} 六根數無法轉成狀態：{exc}") from exc
            states[side] = np.asarray(r, dtype=float), np.asarray(v, dtype=float)
        else:
            states[side] = np.asarray(entry["r_km"], dtype=float), np.asarray(entry["v_kms"], dtype=float)
        epochs[side] = _field(record, ship, "UTCGregorian")
    t_sec = _field(record, seen[mapping["pursuer"]], "ElapsedSecs")
    if t_sec is None:
        t_sec = _field(record, seen[mapping["evader"]], "ElapsedSecs")
    return _finish(states, epochs, t_sec, "gmat", notes + extra + ["取 GMAT 報表最後一列。"])


def _looks_number(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


def _csv_key(key):
    value = key.strip().casefold()
    if value in _NAME_FIELDS:
        return "name"
    if value in _TIME_FIELDS:
        return "epoch" if value in ("epoch", "utcgregorian", "utcg​​regorian") else "time"
    compact = re.sub(r"[\s_()/]", "", value)
    if re.fullmatch(r"r?[xyz](?:km)?", compact):
        axis = compact[1] if compact.startswith("r") else compact[0]
        return axis
    if re.fullmatch(r"v[xyz](?:kms|kmps)?", compact):
        return compact[:2]
    return None


def _read_csv(lines, notes, names, order):
    delimiter = ";" if ";" in lines[0][1] and "," not in lines[0][1] else ","
    rows = [(line, next(csv.reader([raw], delimiter=delimiter))) for line, raw in lines]
    first = rows[0][1]
    fields = [_csv_key(key) for key in first]
    has_header = any(field is not None for field in fields)
    if has_header:
        missing = [key for key in CART if key.lower() not in fields]
        extra = [first[i] for i, field in enumerate(fields) if field is None]
        duplicate = [field for field in set(fields) if field is not None and fields.count(field) > 1]
        if missing or extra or duplicate:
            raise StateImportError(f"CSV 表頭缺欄 {missing}、多欄 {extra}、重複欄 {duplicate}；"
                                   "請用 name, x, y, z, vx, vy, vz（km、km/s）")
        data = rows[1:]
        if len(data) != 2:
            raise StateImportError(f"CSV 表頭後應有追方與逃方各一列，實際有 {len(data)} 列；請檢查缺列或多列")
        seen = []
        states = []
        times = []
        for line, row in data:
            if len(row) != len(first):
                raise StateImportError(f"CSV 第 {line} 列有 {len(row)} 欄，表頭有 {len(first)} 欄；請檢查缺欄或多欄")
            values = {}
            for i, field in enumerate(fields):
                if field in ("x", "y", "z", "vx", "vy", "vz"):
                    values[field] = _number(row[i], line, i + 1)
            states.append((np.asarray([values[k] for k in ("x", "y", "z")], dtype=float),
                           np.asarray([values[k] for k in ("vx", "vy", "vz")], dtype=float)))
            seen.append(row[fields.index("name")].strip() if "name" in fields else None)
            one_time = {}
            if "epoch" in fields and row[fields.index("epoch")].strip():
                i = fields.index("epoch")
                one_time["epoch"] = _epoch(row[i], line, i + 1)
            if "time" in fields and row[fields.index("time")].strip():
                i = fields.index("time")
                cell = row[i].strip()
                one_time["t_sec"] = _number(cell, line, i + 1) if _looks_number(cell) else None
                if one_time["t_sec"] is None:
                    one_time["epoch"] = _epoch(cell, line, i + 1)
            times.append(one_time)
        mapping, extra = _resolve_names(seen, names, order, unlabeled="name" not in fields)
        mapped = {side: states[i] for side, i in mapping.items()}
        epochs = {side: times[i].get("epoch") for side, i in mapping.items()}
        elapsed = [value["t_sec"] for value in times if value.get("t_sec") is not None]
        if len(elapsed) == 2 and elapsed[0] != elapsed[1]:
            raise StateImportError("CSV 兩艘的經過秒數不同；請確認兩列是同一回合的狀態")
        return _finish(mapped, epochs, elapsed[0] if elapsed else None, "csv", notes + extra)
    if len(rows) == 1 and len(first) == 12:
        line = rows[0][0]
        return _finish({"pursuer": _six(first[:6], line), "evader": _six(first[6:], line, 7)},
                       {}, None, "csv", notes + ["CSV 無表頭寬表：前六個數字當追方，後六個當逃方。"])
    if len(rows) == 2 and all(len(row) in (6, 7) for _, row in rows):
        seen = [row[0].strip() if len(row) == 7 else None for _, row in rows]
        mapping, extra = _resolve_names(seen, names, order, unlabeled=seen == [None, None])
        states = [_six(row[1:] if len(row) == 7 else row, line, 2 if len(row) == 7 else 1) for line, row in rows]
        return _finish({side: states[i] for side, i in mapping.items()}, {}, None, "csv", notes + extra)
    raise StateImportError("CSV 要有表頭及兩艘資料列，或一列 12 個數字；請檢查逗號／分號、缺欄與多欄")


def _read_text(lines, notes, names, order):
    if len(lines) == 1:
        line, raw = lines[0]
        values = raw.split()
        if len(values) != 12:
            raise StateImportError(f"純文字第 {line} 列應有 12 個數字，實際有 {len(values)} 欄；請檢查缺欄或多欄")
        return _finish({"pursuer": _six(values[:6], line), "evader": _six(values[6:], line, 7)},
                       {}, None, "text", notes + ["一列 12 數字：前六個當追方，後六個當逃方。"])
    if len(lines) != 2:
        raise StateImportError(f"純文字須有兩列各六個數字，或一列 12 個數字；目前有 {len(lines)} 列。"
                               "請刪除多餘列，# 開頭可作註解")
    seen, states = [], []
    for line, raw in lines:
        values = raw.split()
        if len(values) == 7:
            seen.append(values[0])
            states.append(_six(values[1:], line, 2))
        else:
            seen.append(None)
            states.append(_six(values, line))
    mapping, extra = _resolve_names(seen, names, order, unlabeled=seen == [None, None])
    return _finish({side: states[i] for side, i in mapping.items()}, {}, None, "text", notes + extra)


def read_official_state(path, fmt="auto", names=None, order=None) -> dict:
    """讀官方狀態；格式可為 auto、gmat、csv、json、text。

    epoch 是共同 UTC 時刻；若兩艘 epoch 不同，額外的 ship_epochs 保留各自時刻供初始狀態對齊。
    """
    try:
        with open(path, encoding="utf-8-sig") as source:
            content = source.read()
    except FileNotFoundError as exc:
        raise StateImportError(f"找不到狀態檔 {str(path)!r}；請確認 USB 檔已複製、檔名與目前工作目錄") from exc
    except (OSError, UnicodeError) as exc:
        raise StateImportError(f"無法讀取狀態檔 {str(path)!r}：{exc}；請確認檔案是 UTF-8 文字") from exc
    lines = [(line, raw.strip()) for line, raw in enumerate(content.splitlines(), 1)
             if raw.strip() and not raw.lstrip().startswith("#")]
    if not lines:
        raise StateImportError(f"狀態檔 {str(path)!r} 是空的；請複製含雙方狀態的檔案")
    fmt = str(fmt).casefold()
    notes = []
    if fmt == "auto":
        first = lines[0][1]
        if first.startswith(("{", "[")):
            fmt = "json"
            reason = "首個非註解字元是 JSON 括號"
        elif "," in first or ";" in first:
            fmt = "csv"
            reason = "首列含逗號或分號"
        elif any("." in token and not _looks_number(token) for token in first.split()):
            fmt = "gmat"
            reason = "首列有 Ship.欄位名形式的 GMAT 表頭"
        else:
            fmt = "text"
            reason = "首列是空白分隔數字或名稱，沒有 GMAT 表頭"
        notes.append(f"自動判斷為 {fmt}：{reason}。")
    if fmt not in ("gmat", "csv", "json", "text"):
        raise StateImportError(f"不認得格式 {fmt!r}；請用 auto、gmat、csv、json 或 text")
    if fmt == "json":
        return _read_json(content, notes, names, order)
    if fmt == "gmat":
        return _read_gmat(lines, notes, names, order)
    if fmt == "csv":
        return _read_csv(lines, notes, names, order)
    return _read_text(lines, notes, names, order)


def manual_entry(input_fn=input, print_fn=print) -> dict:
    """逐欄輸入雙方狀態；每項檢查數字與明顯的單位錯誤。"""
    labels = {"pursuer": "追方", "evader": "逃方"}
    while True:
        states = {}
        for side in _SIDES:
            while True:
                values = []
                for key in CART:
                    unit = "km/s" if key.startswith("V") else "km"
                    while True:
                        raw = input_fn(f"{labels[side]} {key}（{unit}）：")
                        try:
                            x = float(raw)
                        except (TypeError, ValueError):
                            print_fn(f"{key} 不是數字；請重新輸入，{unit} 為單位。")
                            continue
                        if not math.isfinite(x):
                            print_fn(f"{key} 不是有限數字；請重新輸入。")
                            continue
                        if key.startswith("V") and abs(x) > 100:
                            print_fn(f"{key}={x:g} 看起來是 m/s；請除以 1000，改填 km/s。")
                            continue
                        if not key.startswith("V") and abs(x) > 1e6:
                            print_fn(f"{key}={x:g} 看起來是公尺；請除以 1000，改填 km。")
                            continue
                        values.append(x)
                        break
                state = np.asarray(values[:3], dtype=float), np.asarray(values[3:], dtype=float)
                try:
                    _validate_ship(side, state)
                except StateImportError as exc:
                    print_fn(f"{exc}；請重新輸入{labels[side]}六個數字。")
                    continue
                states[side] = state
                break
        try:
            result = _finish(states, {}, None, "manual", ["人工逐項輸入；請與官方檔案再次核對。"])
        except StateImportError as exc:
            print_fn(f"{exc}；請重新輸入雙方狀態。")
            continue
        print_fn("請核對輸入摘要（EarthMJ2000Eq；位置 km、速度 km/s）：")
        for side in _SIDES:
            r, v = states[side]
            print_fn(f"{labels[side]}：r=({r[0]:.9f}, {r[1]:.9f}, {r[2]:.9f}) km；"
                     f"v=({v[0]:.9f}, {v[1]:.9f}, {v[2]:.9f}) km/s；"
                     f"|r|={np.linalg.norm(r):.3f} km，|v|={np.linalg.norm(v):.6f} km/s")
        while True:
            answer = input_fn("確認正確？(y/n)：").strip().casefold()
            if answer in ("y", "yes"):
                return result
            if answer in ("n", "no"):
                print_fn("重新輸入雙方狀態。")
                break
            print_fn("請輸入 y 或 n。")
