"""解析官方狀態檔（parse 認得的任何格式），印摘要並另存成 role_select／new 都吃的 JSON。

用金牌賽的 venv、在 medal/ 底下跑：
    .venv/bin/python ../gui/drl_state_to_json.py day/<USB檔> day/initial_state.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.getcwd())

from final_copilot import _parse_names, _parse_state, _print_state  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("out")
    ap.add_argument("--names")
    ap.add_argument("--order")
    args = ap.parse_args()
    state, notes = _parse_state(args.path, names=_parse_names(args.names), order=args.order)
    _print_state(state)
    for note in notes:
        print(f"  解析註記：{note}")
    # 兩艘已對齊到同一個回合起點，只留 r、v（role_select 要求 epoch 雙方都給或都不給）
    out = {side: {"r_km": state[side]["r_km"], "v_kms": state[side]["v_kms"]} for side in ("pursuer", "evader")}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"已另存：{args.out}（角色選擇器與建 session 都可以用這個檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
