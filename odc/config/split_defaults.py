# 此模組負責拆棒策略缺鍵時採用的共用預設。
# 主要入口為 SPLIT_DEFAULTS，計算本體沿用原實作。
"""拆棒設定的共用預設；只有缺鍵時套用，明確的 null／0 留給呼叫端處理。"""

SPLIT_DEFAULTS = {
    "SPLIT_JACOBIAN": "stm",
    "SPLIT_WORKERS": 3,
    "SPLIT_MULTISTART": [0, 0.75, 1],
    "SPLIT_PRUNE_REOPT_MPS": 1.0,
    "SPLIT_WALL_BUDGET_SEC": 600,
}
