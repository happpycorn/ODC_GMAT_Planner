"""評測統計：Wilson 區間、逐局配對（同一批幾何）與符號檢定。

同一批 (規則, 幾何) 上比兩個條件（換大腦、換規則、改程式前後）時，逐局配對比整體勝率
敏感得多：只看「一邊贏、另一邊輸」的局（discordant pairs），用精確二項分布做雙尾符號檢定。

    from evaluation.stats import paired, sign_test
    p = paired(results_a, results_b, win="pursuer")   # tournament 的逐局結果（jsonl 讀回來的 dict）
    print(p["only_a"], p["only_b"], p["p_sign"])
"""
import math

from evaluation.tournament import wilson


def sign_test(only_a: int, only_b: int) -> float:
    """雙尾精確符號檢定：H0 = 配對差異方向是公平硬幣。回傳 p 值（沒有不一致的局時 = 1）。"""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n
    return min(1.0, 2.0 * tail)


def _key(r):
    return (r["game_id"], r.get("family"))


def paired(results_a, results_b, win="pursuer"):
    """兩組逐局結果依 game_id 配對（只取兩邊都有的局），算各種組合的局數與符號檢定。

    win：以哪一方贏當「成功」（pursuer = 追者勝/捕獲，evader = 躲者存活）。"""
    a = {_key(r): r["winner"] == win for r in results_a}
    b = {_key(r): r["winner"] == win for r in results_b}
    common = sorted(set(a) & set(b))
    both = sum(a[k] and b[k] for k in common)
    only_a = sum(a[k] and not b[k] for k in common)
    only_b = sum(b[k] and not a[k] for k in common)
    n = len(common)
    ka, kb = both + only_a, both + only_b
    return {
        "n": n, "both": both, "only_a": only_a, "only_b": only_b, "neither": n - both - only_a - only_b,
        "rate_a": ka / n if n else math.nan, "ci_a": wilson(ka, n),
        "rate_b": kb / n if n else math.nan, "ci_b": wilson(kb, n),
        "p_sign": sign_test(only_a, only_b),
    }


def format_paired(p, label_a="A", label_b="B", win="pursuer"):
    what = "追者勝率" if win == "pursuer" else "躲者存活"
    return (f"{what}：{label_a} {100 * p['rate_a']:.0f}% [{100 * p['ci_a'][0]:.0f}–{100 * p['ci_a'][1]:.0f}] vs "
            f"{label_b} {100 * p['rate_b']:.0f}% [{100 * p['ci_b'][0]:.0f}–{100 * p['ci_b'][1]:.0f}]（n={p['n']}）；"
            f"逐局：兩邊都成功 {p['both']}、只有 {label_a} {p['only_a']}、只有 {label_b} {p['only_b']}、"
            f"都沒有 {p['neither']}；符號檢定 p = {p['p_sign']:.3g}")
