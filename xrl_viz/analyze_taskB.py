#!/usr/bin/env python3
"""analyze_taskB.py — §2.3（上位2手の訪問数タイ）の検証と，tree_json の欠落調査．

対象は修正後データ xrl_viz/data/sweep_postfix/post_n{16,32,128}.json．

出力（xrl_viz/data/analysis_taskB/）:
  survivors_n{N}.csv  … ply ごとの生存手・訪問数・タイ判定（Step 1）
  missing_n{N}.csv    … ply ごとの「木に現れない合法手」（Step 0-2）
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_alignment import legal_moves, aid_to_coord as _aid_to_coord  # noqa: E402


def coord(aid, b):
    """check_alignment 版は PASS で None を返すので，表示用に "PASS" を返す版を使う．
    根拠: sgf_loader.cpp L105 … action_id == board_size*board_size が PASS．"""
    return _aid_to_coord(aid, b) or ("PASS" if aid == b * b else f"?{aid}")

LEVELS = (16, 32, 128)
SRC = "xrl_viz/data/sweep_postfix/post_n{}.json"
OUT = "xrl_viz/data/analysis_taskB"


def count_nodes(node):
    """tree_json に実際に出ている子孫ノード数（root を除く）を数える．"""
    n = 0
    for c in node.get("children", []):
        n += 1 + count_nodes(c)
    return n


def analyze(n):
    d = json.load(open(SRC.format(n)))
    b = d["board_size"]
    surv_rows, miss_rows = [], []
    tie_ok = tie_ng = surv_not2 = 0
    total_nodes = 0

    for mv in d["moves"]:
        ply, root, played = mv["ply"], mv["root"], mv["played"]
        kids = root.get("children", [])
        total_nodes += count_nodes(root)

        # --- Step 0-2: 木に現れない合法手 ---
        legal = legal_moves(mv["board"], mv["to_play"], b)
        legal_coord = {f"{chr(ord('A') + c)}{r + 1}" for r, c in legal}
        present = {coord(c["action_id"], b) for c in kids}
        missing = sorted(legal_coord - present)
        k = len(legal_coord)
        miss_rows.append({
            "ply": ply, "to_play": mv["to_play"], "k": k,
            "tree_children": len(kids), "missing": len(missing),
            "expected_missing_if_only_topm": max(0, k - 16),
            "matches_topm_rule": len(missing) == max(0, k - 16),
            "missing_moves": " ".join(missing),
        })

        # --- Step 1: 生存手とタイ判定 ---
        surv = [c for c in kids if c.get("gaz_eliminated_round") == -1]
        surv.sort(key=lambda c: -c["N"])
        ns = [c["N"] for c in surv]
        is2 = len(surv) == 2
        tie = (is2 and ns[0] == ns[1])
        if not is2:
            surv_not2 += 1
        elif tie:
            tie_ok += 1
        else:
            tie_ng += 1
        played_is_surv = played in {coord(c["action_id"], b) for c in surv}
        surv_rows.append({
            "ply": ply, "to_play": mv["to_play"], "played": played, "k": k,
            "n_children": len(kids),
            "n_survivors": len(surv),
            "survivors": " ".join(coord(c["action_id"], b) for c in surv),
            "survivor_N": " ".join(str(x) for x in ns),
            "survivors_are_2": is2,
            "top2_N_equal": tie if is2 else "",
            "top2_N_diff": (ns[0] - ns[1]) if is2 else "",
            "played_is_survivor": played_is_surv,
            "all_N": " ".join("{}:{}".format(coord(c["action_id"], b), c["N"]) for c in
                              sorted(kids, key=lambda c: -c["N"])),
        })

    os.makedirs(OUT, exist_ok=True)
    for name, rows in (("survivors", surv_rows), ("missing", miss_rows)):
        p = f"{OUT}/{name}_n{n}.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    size = os.path.getsize(SRC.format(n))
    n_missing_root = sum(r["missing"] for r in miss_rows)
    rule_ok = all(r["matches_topm_rule"] for r in miss_rows)

    print(f"=== n={n} ===")
    print(f"  [Step 0-2] 木に現れない合法手 合計 {n_missing_root} 手 / "
          f"「top-m から漏れた分だけ」と一致: {rule_ok}")
    print(f"  [Step 0-3] 現ファイル {size:,} bytes / 出力ノード総数 {total_nodes:,}")
    print(f"  [Step 1] 生存手がちょうど2手でない ply: {surv_not2}/{len(surv_rows)}")
    print(f"  [Step 1] 生存2手の N が一致: {tie_ok} / 不一致: {tie_ng}"
          + (f"  → 一致率 {tie_ok}/{tie_ok + tie_ng}" if (tie_ok + tie_ng) else ""))
    if tie_ng:
        ex = [r for r in surv_rows if r["survivors_are_2"] and not r["top2_N_equal"]][:6]
        for r in ex:
            print(f"     ply {r['ply']}: {r['survivors']} = {r['survivor_N']} (差 {r['top2_N_diff']})")
    if surv_not2:
        ex = [r for r in surv_rows if not r["survivors_are_2"]][:6]
        for r in ex:
            print(f"     生存{r['n_survivors']}手: ply {r['ply']} k={r['k']} {r['survivors']}")
    npl = sum(1 for r in surv_rows if not r["played_is_survivor"])
    print(f"  [Step 1] 着手が生存手でなかった ply: {npl}/{len(surv_rows)}")
    print()
    return total_nodes, size


if __name__ == "__main__":
    for n in LEVELS:
        analyze(n)
