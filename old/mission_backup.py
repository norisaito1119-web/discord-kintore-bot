
MONTHLY_MISSIONS = [
    {"body_part": "胸", "type": "weight", "exercise": "ダンベル", "target": 20},
    {"body_part": "背中", "type": "count", "exercise": "懸垂マシン", "target": 5},
    {"body_part": "脚", "type": "weight", "exercise": "ダンベル", "target": 8},
]

#[M3-1]月間ミッションチェック
def ck_mon_mission(rows, mission):
    matched_weights = []
    matched_count = 0

    for body_part, exercise, weight, sets in rows:
        if mission["exercise"] in exercise:
            matched_weights.append(weight)
            matched_count += 1

    if mission["type"] == "weight":
        #三項演算子:[値A] if [条件] else [値B] T→値A F→[値B]
        curr = max(matched_weights) if matched_weights else 0
    else:
        curr = matched_count

    sts_flg = curr >= mission["target"]
    return sts_flg, curr
