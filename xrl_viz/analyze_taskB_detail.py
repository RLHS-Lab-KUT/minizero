#!/usr/bin/env python3
"""analyze_taskB_detail.py — Task B の追い込み調査．

  (1) n=32 で生存2手の N が一致しなかった ply の差の分布
  (2) 「着手が生存手でない」ply の正体
  (3) displayInTreeLog のフィルタを外した場合の出力ノード数（実測・推定ではない）
      木を辿りながら盤面を進め，各展開ノードの合法手数を数える．
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_alignment import legal_moves, DIRS  # noqa: E402

LEVELS = (16, 32, 128)
SRC = "xrl_viz/data/sweep_postfix/post_n{}.json"


def coord(aid, b):
    if aid == b * b:
        return "PASS"
    x, y = aid % b, aid // b
    return f"{chr(ord('A') + x + (1 if x >= 8 else 0))}{y + 1}"


def apply_move(board, player, aid, b):
    """着手を適用した新しい盤面を返す．PASS は盤面を変えない．
    反転規則は check_alignment.legal_moves と同じ8方向走査．"""
    if aid == b * b:
        return [row[:] for row in board]
    r, c = aid // b, aid % b
    opp = "W" if player == "B" else "B"
    nb = [row[:] for row in board]
    nb[r][c] = player
    for dr, dc in DIRS:
        rr, cc, run = r + dr, c + dc, []
        while 0 <= rr < b and 0 <= cc < b and nb[rr][cc] == opp:
            run.append((rr, cc))
            rr += dr
            cc += dc
        if run and 0 <= rr < b and 0 <= cc < b and nb[rr][cc] == player:
            for (xr, xc) in run:
                nb[xr][xc] = player
    return nb


def walk(node, board, player, b, acc):
    """出力済みノード数と，フィルタを外した場合のノード数を数える．"""
    opp = "W" if player == "B" else "B"
    kids = node.get("children", [])
    if kids:
        # この局面は展開済み．フィルタを外すと合法手の数だけ子が出る．
        nlegal = len(legal_moves(board, player, b))
        acc["unfiltered"] += max(nlegal, 1)  # 合法手0なら PASS の子が1つ
        acc["current"] += len(kids)
        for c in kids:
            nb = apply_move(board, player, c["action_id"], b)
            walk(c, nb, opp, b, acc)


def main():
    for n in LEVELS:
        d = json.load(open(SRC.format(n)))
        b = d["board_size"]
        diffs = Counter()
        not_surv = []
        acc = {"current": 0, "unfiltered": 0}
        for mv in d["moves"]:
            kids = mv["root"].get("children", [])
            surv = sorted([c for c in kids if c.get("gaz_eliminated_round") == -1],
                          key=lambda c: -c["N"])
            if len(surv) == 2 and surv[0]["N"] != surv[1]["N"]:
                diffs[surv[0]["N"] - surv[1]["N"]] += 1
            if mv["played"] not in {coord(c["action_id"], b) for c in surv}:
                not_surv.append((mv["ply"], mv["played"], len(surv),
                                 [coord(c["action_id"], b) for c in surv]))
            walk(mv["root"], mv["board"], mv["to_play"], b, acc)

        print(f"=== n={n} ===")
        print(f"  生存2手の N の差の分布: {dict(sorted(diffs.items()))}")
        print(f"  着手が生存手でない ply: {len(not_surv)} -> {not_surv[:6]}")
        size = os.path.getsize(SRC.format(n))
        ratio = acc["unfiltered"] / acc["current"] if acc["current"] else 0
        print(f"  出力ノード数 現在 {acc['current']:,} / フィルタ除去時 {acc['unfiltered']:,}"
              f"  ({ratio:.2f} 倍)")
        print(f"  ファイルサイズ 現在 {size:,} bytes / 概算 {int(size * ratio):,} bytes")
        print()


if __name__ == "__main__":
    main()
