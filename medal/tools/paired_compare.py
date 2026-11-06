"""逐局配對比較兩組評測結果（evaluate.py 的 reports/*.jsonl），附 Wilson 區間與符號檢定。

兩組必須是同一批幾何（同 --seed、同 --scenario、同 --games 的 evaluate.py 輸出，game_id 對得上）。
每組用「檔案 + 追者名稱 + 躲者名稱」指定一個配對；名稱就是報表上的名字（spec_name），
省略時檔案裡只能有一種追者（或躲者）。

例：
    # 同一個檔案裡比兩個追者大腦（對同一個躲者）
    uv run python tools/paired_compare.py --a reports/x.jsonl --ap rollout_pursuer --ae rollout_evader \
        --b reports/x.jsonl --bp lambert_pursuer --be rollout_evader
    # 改程式前後 / 換規則：兩個檔案、同一組配對
    uv run python tools/paired_compare.py --a reports/before.jsonl --b reports/after.jsonl \
        --ap rollout_pursuer --ae rollout_evader --win evader
    # 列出檔案裡有哪些配對
    uv run python tools/paired_compare.py --a reports/x.jsonl --list
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.stats import format_paired, paired  # noqa: E402


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def pick(rows, pursuer, evader, path):
    for side, want in (("pursuer", pursuer), ("evader", evader)):
        names = sorted({r[side] for r in rows})
        if want is None:
            if len(names) != 1:
                raise SystemExit(f"{path} 有多個 {side}：{names}，請指定名稱")
        elif want not in names:
            raise SystemExit(f"{path} 沒有 {side} {want!r}；有：{names}")
    return [r for r in rows if (pursuer is None or r["pursuer"] == pursuer) and (evader is None or r["evader"] == evader)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", default=None, help="預設同 --a")
    ap.add_argument("--ap", default=None, help="A 組追者名稱")
    ap.add_argument("--ae", default=None, help="A 組躲者名稱")
    ap.add_argument("--bp", default=None, help="B 組追者名稱（預設同 --ap）")
    ap.add_argument("--be", default=None, help="B 組躲者名稱（預設同 --ae）")
    ap.add_argument("--win", default="pursuer", choices=["pursuer", "evader"], help="以哪方贏當成功")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    rows_a = load(args.a)
    if args.list:
        pairs = sorted({(r["pursuer"], r["evader"]) for r in rows_a})
        for p, e in pairs:
            n = sum(r["pursuer"] == p and r["evader"] == e for r in rows_a)
            print(f"{n:4d}  追者 {p}   躲者 {e}")
        return
    rows_b = load(args.b) if args.b else rows_a
    a = pick(rows_a, args.ap, args.ae, args.a)
    b = pick(rows_b, args.bp or args.ap, args.be or args.ae, args.b or args.a)
    print(format_paired(paired(a, b, args.win), args.label_a, args.label_b, args.win))


if __name__ == "__main__":
    main()
