#!/usr/bin/env python3
"""PV（打った手の下で最大訪問の子）が実際の相手応手を予測できているかを n 水準ごとに測定する。

測定:
  (1) 応手を予測できた ply … 打った手のノードの下に子(N>=1)が1つ以上ある ply
  (2) 予測の的中率     … 打った手の下の PV(=最大N の子)が、実際の次 ply の着手と一致
  (3) 予測に使えた情報量 … 打った手の訪問数 N の中央値／子の数の中央値

除外: 投了(Resign)以降の ply、PASS の ply、および played が PASS/Resign の ply。
"""
import glob
import json
import re
import statistics as st

COLS = "ABCDEFGH"


def coord(k):
    if k.get("row") is None or k.get("col") is None:
        return "PASS"
    return COLS[k["col"]] + str(k["row"] + 1)


def median(xs):
    return st.median(xs) if xs else None


def analyze(path):
    d = json.load(open(path))
    ms = d["moves"]

    # 投了以降を除外
    resign_ply = next((m["ply"] for m in ms if m.get("played") == "Resign"), None)

    # ply -> 実際の着手（全 ply、次手参照用）
    played_by_ply = {m["ply"]: m.get("played") for m in ms}

    predictable = 0          # (1) 分子: 子>=1 の ply
    evaluable = 0            # (1)(3) 分母: 除外後に残った通常着手 ply
    hit = 0                  # (2) 分子: PV 的中
    predict_with_target = 0  # (2) 分母: 予測可能かつ次手が実座標
    next_terminal = 0        # 予測可能だが次手が PASS/Resign で照合不能
    n_played = []            # (3) 打った手の N
    n_children = []          # (3) 打った手の子の数
    by_kidcount = []         # (子数, 的中?) 層別用

    for i, m in enumerate(ms):
        ply = m["ply"]
        if resign_ply is not None and ply >= resign_ply:
            continue
        pl = m.get("played")
        if pl in (None, "PASS", "Resign"):
            continue

        # 打った手に対応する root の子
        kids_root = m["root"].get("children", [])
        pc = next((c for c in kids_root if coord(c) == pl), None)
        if pc is None:
            # 着手がツリーに無い（想定外）。除外して記録。
            continue

        evaluable += 1
        kids = pc.get("children", [])  # 実データ上すべて N>=1
        n_played.append(pc["N"])
        n_children.append(len(kids))

        if not kids:
            continue  # 子ゼロ → 予測不能
        predictable += 1

        pv = max(kids, key=lambda c: c["N"])
        pv_move = coord(pv)

        actual_next = played_by_ply.get(ply + 1)
        if actual_next in (None, "PASS", "Resign"):
            next_terminal += 1
            continue
        predict_with_target += 1
        is_hit = pv_move == actual_next
        if is_hit:
            hit += 1
        by_kidcount.append((len(kids), is_hit))

    return {
        "plies": len(ms),
        "resign_ply": resign_ply,
        "evaluable": evaluable,
        "predictable": predictable,
        "hit": hit,
        "predict_with_target": predict_with_target,
        "next_terminal": next_terminal,
        "med_N": median(n_played),
        "med_children": median(n_children),
        "n_played": n_played,
        "n_children": n_children,
        "by_kidcount": by_kidcount,
    }


def main():
    files = []
    for f in glob.glob("xrl_viz/data/sweep/n*_eval_*.json"):
        mo = re.search(r"n(\d+)_eval_", f)
        if mo:
            files.append((int(mo.group(1)), f))
    files.sort()

    rows = [(n, analyze(p)) for n, p in files]

    print("=" * 100)
    print("PV による相手応手の予測可能性・的中率（1 対局 / 水準）")
    print("=" * 100)

    print("\n[1] 応手を予測できた ply の数と割合（打った手の下に子>=1）")
    print(f"{'n':>5} | {'評価対象ply':>10} | {'予測できたply':>12} | {'割合':>7} | {'投了ply':>7}")
    print("-" * 60)
    for n, r in rows:
        ratio = r["predictable"] / r["evaluable"] if r["evaluable"] else 0
        print(f"{n:>5} | {r['evaluable']:>10} | {r['predictable']:>12} | "
              f"{ratio:>6.1%} | {str(r['resign_ply']):>7}")

    print("\n[1b] 応手を「複数」比較できた ply（子>=2 = 2通り以上の応手を試した）")
    print(f"{'n':>5} | {'評価対象ply':>10} | {'子>=2 のply':>11} | {'割合':>7} | {'子=1(第一感1回)':>14}")
    print("-" * 62)
    for n, r in rows:
        ge2 = sum(1 for x in r["n_children"] if x >= 2)
        eq1 = sum(1 for x in r["n_children"] if x == 1)
        ratio = ge2 / r["evaluable"] if r["evaluable"] else 0
        print(f"{n:>5} | {r['evaluable']:>10} | {ge2:>11} | {ratio:>6.1%} | {eq1:>14}")

    print("\n[2] 予測の的中率（PV = 打った手の下で最大 N の子 が実際の次手と一致）")
    print(f"{'n':>5} | {'照合可能ply':>10} | {'的中':>5} | {'的中率':>7} | {'次手が終局で除外':>14}")
    print("-" * 62)
    for n, r in rows:
        dv = r["predict_with_target"]
        acc = r["hit"] / dv if dv else 0
        print(f"{n:>5} | {dv:>10} | {r['hit']:>5} | {acc:>6.1%} | {r['next_terminal']:>14}")

    print("\n[3] 予測に使えた情報量（評価対象 ply 全体の中央値）")
    print(f"{'n':>5} | {'打った手 N 中央値':>16} | {'子の数 中央値':>13} | {'N=1(予測不能)の ply 数':>22}")
    print("-" * 66)
    for n, r in rows:
        n1 = sum(1 for x in r["n_played"] if x == 1)
        print(f"{n:>5} | {str(r['med_N']):>16} | {str(r['med_children']):>13} | {n1:>22}")

    # 参考: N の分布
    print("\n[参考] 打った手の訪問数 N の分布（評価対象 ply）")
    print(f"{'n':>5} | {'min':>4} {'p25':>5} {'中央':>5} {'p75':>5} {'max':>5} | {'子の数 min/中央/max':>18}")
    print("-" * 60)
    for n, r in rows:
        xs = sorted(r["n_played"])
        cs = sorted(r["n_children"])

        def q(a, p):
            if not a:
                return 0
            k = max(0, min(len(a) - 1, int(round(p * (len(a) - 1)))))
            return a[k]
        print(f"{n:>5} | {xs[0]:>4} {q(xs, .25):>5} {q(xs, .5):>5} {q(xs, .75):>5} {xs[-1]:>5} | "
              f"{cs[0]:>3}/{q(cs, .5)}/{cs[-1]:<3}")

    # 全水準プールして、比較した応手数(子数)で的中率を層別
    print("\n[4] 子の数（比較した応手数）で層別した的中率【全 n プール】")
    print("   仮説の直接検証: 多くの応手を比較したときほど予測が当たるか")
    print(f"{'子の数':>8} | {'照合ply':>7} | {'的中':>5} | {'的中率':>7}")
    print("-" * 40)
    pool = [pair for _, r in rows for pair in r["by_kidcount"]]
    buckets = {"1": [x for x in pool if x[0] == 1],
               "2": [x for x in pool if x[0] == 2],
               "3": [x for x in pool if x[0] == 3],
               ">=4": [x for x in pool if x[0] >= 4]}
    for lab, b in buckets.items():
        if not b:
            continue
        h = sum(1 for _, hit in b if hit)
        print(f"{lab:>8} | {len(b):>7} | {h:>5} | {h / len(b):>6.1%}")


if __name__ == "__main__":
    main()
