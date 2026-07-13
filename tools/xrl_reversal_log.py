#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xrl_reversal_log.py  (v2)
xrl_viz/index.html と同じ game.json / 単一 tree_json をそのまま入力に取り、
root-level の「Q値の逆転」「方策(p)近接」を検出して JSONL ログ化＋頻度統計を出す。
C++ 改修は不要。

Viewer 整合（xrl_viz/index.html 9a1f748 に準拠）:
  - game.json   = {game, board_size, moves:[{ply, played, to_play, board, root}, ...]}
  - 単一tree_json = {game, board_size, to_play, board, root}  → 1手の game とみなす
  - played は "F4" 形式の文字列(着手)。座標 = COLS[col]+(row+1), COLS="ABCDEFGH"
  - Viewer の「最大P」はノイズ込み P。本ツールは第一感を p_logit で取り、参考に P 版も出す。

注意（実コード由来の事実）:
  - Q は生 getMean()。探索が比較する getNormalizedMean() とは別物。
  - PV(Viewer の緑) は最大N経路であって最大Q経路ではない(markPV)。
  - variance は tree_json に無い → 有意性は当面 ε(=Qマージン閾値)で代用。
"""
import json
import argparse
from collections import defaultdict

COLS = "ABCDEFGH"          # Viewer と同一(オセロ8x8専用)
TIE_EPS = 1e-6             # float 同点判定の許容誤差


def coord_of(child):
    # 盤外 action(=PASS)は tree_json 側で row/col=null。null安全に "PASS" を返す。
    if child.get("row") is None or child.get("col") is None:
        return "PASS"
    return COLS[child["col"]] + str(child["row"] + 1)


def _ties(children, key):
    best = max(key(c) for c in children)
    return best, [c for c in children if abs(key(c) - best) <= TIE_EPS]


def _top2_margin(children, key):
    vs = sorted((key(c) for c in children), reverse=True)
    return (vs[0] - vs[1]) if len(vs) >= 2 else float("inf")


def resolve_played(children, played):
    """played("F4" or action_id or None) を root child の action_id に解決。"""
    if played is None:
        return None
    if isinstance(played, int):
        return played
    p = str(played).strip().upper()
    for c in children:
        if coord_of(c).upper() == p:
            return c["action_id"]
    return None  # PASS や不一致は None


def analyze_position(move, game_id=None):
    """move = game.json の1要素 {ply, played, to_play, root, ...} もしくは単一tree_json。"""
    root = move["root"]
    children = [c for c in root.get("children", []) if c["N"] > 0]
    if not children:
        return None
    played_aid = resolve_played(children, move.get("played"))

    bestN, tN = _ties(children, lambda c: c["N"])
    bestQ, tQ = _ties(children, lambda c: c["Q"])
    bestPL, tPL = _ties(children, lambda c: c["p_logit"])   # クリーン第一感
    bestPn, tPn = _ties(children, lambda c: c["P"])         # ノイズ込み(Viewer整合)

    aN = sorted(c["action_id"] for c in tN)
    aQ = sorted(c["action_id"] for c in tQ)
    aPL = sorted(c["action_id"] for c in tPL)
    aPn = sorted(c["action_id"] for c in tPn)
    lab = {c["action_id"]: coord_of(c) for c in children}

    return {
        "game_id": game_id,
        "ply": move.get("ply"),
        "to_play": move.get("to_play") or root.get("player"),
        "played": move.get("played"),
        "played_aid": played_aid,
        "n_sims": root["N"], "n_children": len(children),
        "argmaxN": {"labels": [lab[a] for a in aN], "tie": len(aN) > 1, "N": bestN},
        "argmaxQ": {"labels": [lab[a] for a in aQ], "tie": len(aQ) > 1, "Q": bestQ},
        "argmaxP_logit": {"labels": [lab[a] for a in aPL], "tie": len(aPL) > 1},  # 第一感
        "argmaxP_noisy": {"labels": [lab[a] for a in aPn], "tie": len(aPn) > 1},  # Viewer整合
        "margins": {"q": _top2_margin(children, lambda c: c["Q"]),
                    "p_logit": _top2_margin(children, lambda c: c["p_logit"]),
                    "n": _top2_margin(children, lambda c: c["N"])},
        "flags": {
            "played_ne_argmaxQ": (None if played_aid is None else played_aid not in aQ),   # 型1
            "argmaxN_ne_argmaxQ": (set(aN) != set(aQ)),                                     # 型2
            "argmaxP_ne_argmaxQ": (set(aPL) != set(aQ)),                                    # 型3(クリーン)
            "played_ne_argmaxN": (None if played_aid is None else played_aid not in aN),
            "played_eq_argmaxP_logit": (None if played_aid is None else played_aid in aPL),
        },
        "children": [{"label": coord_of(c), "action_id": c["action_id"],
                      "N": c["N"], "Q": c["Q"], "P": c["P"],
                      "p_logit": c["p_logit"], "v": c["v"]} for c in children],
    }


def iter_moves(obj):
    if isinstance(obj, dict) and "moves" in obj:
        for m in obj["moves"]:
            yield m
    elif isinstance(obj, dict) and "root" in obj:
        yield {"ply": 0, "played": obj.get("played"),
               "to_play": obj.get("to_play"), "root": obj["root"]}


def load_records(path):
    text = open(path).read().strip()
    recs = []
    try:
        obj = json.loads(text)
        gid = obj.get("game") if isinstance(obj, dict) else None
        for m in iter_moves(obj):
            r = analyze_position(m, gid)
            if r:
                recs.append(r)
        return recs
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if "tree_json" in o:
            m = dict(o["tree_json"])
            m["played"] = o.get("played")
            m["ply"] = o.get("move_no")
            r = analyze_position(m, o.get("game_id"))
            if r:
                recs.append(r)
        else:
            for m in iter_moves(o):
                r = analyze_position(m, o.get("game") if isinstance(o, dict) else None)
                if r:
                    recs.append(r)
    return recs


def aggregate(recs, eps_grid=(0.0, 0.005, 0.01, 0.02, 0.05), n_phases=3):
    recs = [r for r in recs if r]
    total = len(recs)
    out = {"total_decisions": total}
    if not total:
        return out
    def rate(pred): return {"count": sum(1 for r in recs if pred(r)),
                            "rate": sum(1 for r in recs if pred(r)) / total}
    out["raw"] = {
        "played_ne_argmaxQ": rate(lambda r: r["flags"]["played_ne_argmaxQ"] is True),
        "argmaxN_ne_argmaxQ": rate(lambda r: r["flags"]["argmaxN_ne_argmaxQ"]),
        "argmaxP_ne_argmaxQ": rate(lambda r: r["flags"]["argmaxP_ne_argmaxQ"]),
        "argmaxN_tie": rate(lambda r: r["argmaxN"]["tie"]),
    }
    out["significant_argmaxN_ne_argmaxQ_by_eps"] = {
        eps: rate(lambda r, e=eps: r["flags"]["argmaxN_ne_argmaxQ"] and r["margins"]["q"] > e)
        for eps in eps_grid}
    phased = [r for r in recs if r.get("ply") is not None]
    if phased:
        mx = max(r["ply"] for r in phased) or 1
        buckets = defaultdict(list)
        for r in phased:
            buckets[min(n_phases - 1, int(r["ply"] / (mx + 1) * n_phases))].append(r)
        out["by_phase"] = {f"phase_{b}": {
            "n": len(rs),
            "argmaxN_ne_argmaxQ": sum(1 for r in rs if r["flags"]["argmaxN_ne_argmaxQ"]) / len(rs)}
            for b, rs in sorted(buckets.items())}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="game.json / 単一tree_json / JSONL")
    ap.add_argument("--out", default=None, help="逆転レコードの出力 JSONL")
    args = ap.parse_args()
    recs = load_records(args.input)
    if args.out:
        with open(args.out, "w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(aggregate(recs), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
