#!/usr/bin/env python3
"""compare_runs.py — 2つの Capture_game.sh 出力を ply 単位で厳密比較する。

Capture_game.sh の ply 数は終局付近のパイプ競合で run ごとにぶれるため、
「共通接頭部で内容が一致するか」で決定論性を判定する。

使い方:
    python3 xrl_viz/compare_runs.py A.json B.json [--gaz]

--gaz を付けると gaz_eliminated_round / gaz_decision_score も比較する
（どちらか片方にしか無い場合は付けない）。
"""
import json
import sys

# 探索の中身を表すフィールド。gaz_* は計装で後から足したので既定では見ない。
CORE_FIELDS = ("action_id", "player", "N", "Q", "P", "p_logit", "p_noise", "v", "r")


def child_key(c):
    return c["action_id"]


def cmp_node(a, b, fields, path, diffs):
    for f in fields:
        if a.get(f) != b.get(f):
            diffs.append(f"{path}: {f} {a.get(f)!r} != {b.get(f)!r}")
    ca = {child_key(c): c for c in a.get("children", [])}
    cb = {child_key(c): c for c in b.get("children", [])}
    if set(ca) != set(cb):
        diffs.append(f"{path}: child set {sorted(set(ca) ^ set(cb))} differs")
        return
    for k in sorted(ca):
        cmp_node(ca[k], cb[k], fields, f"{path}/{k}", diffs)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fields = CORE_FIELDS + (("gaz_eliminated_round", "gaz_decision_score") if "--gaz" in sys.argv else ())
    a = json.load(open(args[0]))["moves"]
    b = json.load(open(args[1]))["moves"]
    common = min(len(a), len(b))
    print(f"A={args[0]} ({len(a)} ply)  B={args[1]} ({len(b)} ply)  common={common}")

    move_diffs, tree_diffs = [], []
    for i in range(common):
        if a[i]["played"] != b[i]["played"]:
            move_diffs.append(f"ply {i}: {a[i]['played']} != {b[i]['played']}")
        if a[i]["board"] != b[i]["board"]:
            tree_diffs.append(f"ply {i}: board differs")
        d = []
        cmp_node(a[i]["root"], b[i]["root"], fields, f"ply{i}", d)
        tree_diffs.extend(d)

    print(f"  着手の差:   {len(move_diffs)}")
    for m in move_diffs[:20]:
        print("    " + m)
    print(f"  探索木の差: {len(tree_diffs)}")
    for m in tree_diffs[:20]:
        print("    " + m)
    if not move_diffs and not tree_diffs:
        print("  => 共通接頭部は完全一致")
    return 1 if (move_diffs or tree_diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
