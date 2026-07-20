#!/usr/bin/env python3
"""analyze_vlfix.py — virtual loss 修正の前後を同一局面で比較する．

入力は replay.py の出力（n16 の局面列を各エンジンに打ち直したもの）なので，
修正前後で完全に同じ局面列を比較できる．自己対戦の記録は最初の着手差以降
局面が分岐するため，この比較には使えない．

比較する量:
  1. エンジンの着手が変わった ply
  2. root 直下の訪問数 N の分布が変わった ply
  3. gaz_eliminated_round（どの候補が何巡目で落ちたか）が変わった ply と巡

gaz_decision_score は比較しない．案B は score の計算式そのものを変えるため，
前後の差はバグの証拠にならない（定義が変わっただけ）．

使い方: python3 xrl_viz/analyze_vlfix.py DIR
        DIR に prefix_n*.json / postfix_n*.json がある前提．
"""
import json
import os
import sys

LEVELS = (16, 32, 128)


def coord(aid, b=8):
    x, y = aid % b, aid // b
    return f"{chr(ord('A') + x + (1 if x >= 8 else 0))}{y + 1}"


def root_children(rec):
    return {c["action_id"]: c for c in rec["tree"]["root"].get("children", [])}


def analyze(d, n):
    a = json.load(open(os.path.join(d, f"prefix_n{n}.json")))
    b = json.load(open(os.path.join(d, f"postfix_n{n}.json")))
    assert len(a) == len(b), f"ply 数が違う: {len(a)} vs {len(b)}"

    move_changed, visit_changed = [], []
    rounds_total = rounds_changed = 0
    elim_changed_plies = set()
    elim_cell_changes = 0

    for ra, rb in zip(a, b):
        ply = ra["ply"]
        if ra["engine_move"].upper() != rb["engine_move"].upper():
            move_changed.append((ply, ra["engine_move"], rb["engine_move"]))

        ca, cb = root_children(ra), root_children(rb)
        na = {k: v["N"] for k, v in ca.items()}
        nb = {k: v["N"] for k, v in cb.items()}
        if na != nb:
            visit_changed.append(ply)

        # 巡ごとの淘汰集合を比べる
        ea = {k: v.get("gaz_eliminated_round") for k, v in ca.items()}
        eb = {k: v.get("gaz_eliminated_round") for k, v in cb.items()}
        if ea != eb:
            elim_changed_plies.add(ply)
            elim_cell_changes += sum(1 for k in set(ea) | set(eb) if ea.get(k) != eb.get(k))
        max_round = max([r for r in list(ea.values()) + list(eb.values())
                         if isinstance(r, int) and r >= 0] or [-1])
        for r in range(max_round + 1):
            rounds_total += 1
            if {k for k, v in ea.items() if v == r} != {k for k, v in eb.items() if v == r}:
                rounds_changed += 1

    print(f"=== n={n}  ({len(a)} ply) ===")
    print(f"  着手が変わった ply: {len(move_changed)}")
    for ply, x, y in move_changed[:12]:
        print(f"     ply {ply}: {x} -> {y}")
    print(f"  root 直下の訪問数分布が変わった ply: {len(visit_changed)}/{len(a)}  {visit_changed[:15]}")
    print(f"  淘汰結果が変わったラウンド数: {rounds_changed}/{rounds_total}")
    print(f"  eliminated_round が変わった ply: {len(elim_changed_plies)}/{len(a)}"
          f"（延べ {elim_cell_changes} 手）")
    return len(move_changed), rounds_changed, rounds_total


if __name__ == "__main__":
    d = sys.argv[1]
    for n in LEVELS:
        analyze(d, n)
        print()
