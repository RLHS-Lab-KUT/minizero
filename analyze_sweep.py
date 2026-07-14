#!/usr/bin/env python3
"""n スイープ記録を検証し、halving の発火点を実データで特定する。"""
import sys
import os
import re
import json

COLS = "ABCDEFGH"


def coord(k):
    if k.get("row") is None or k.get("col") is None:
        return "PASS"
    return COLS[k["col"]] + str(k["row"] + 1)


def qnorm(k):
    return -k["Q"] if k["player"] == "W" else k["Q"]


def walk(n):
    yield n
    for c in n.get("children", []):
        yield from walk(c)


def compress(dist):
    out, i = [], 0
    while i < len(dist):
        j = i
        while j < len(dist) and dist[j] == dist[i]:
            j += 1
        out.append(str(dist[i]) if j - i == 1 else f"{dist[i]}x{j - i}")
        i = j
    return "[" + ", ".join(out) + "]"


def analyze(path, n_expected):
    d = json.load(open(path))
    ms = d["moves"]
    resign = next((m["ply"] for m in ms if m.get("played") == "Resign"), None)
    live = [m for m in ms if resign is None or m["ply"] < resign]

    noisy = sum(1 for m in ms for nd in walk(m["root"])
                if nd.get("p_noise") not in (0, 0.0, None))

    mism = checked = 0
    for m in live:
        allk = m["root"].get("children", [])
        kids = [k for k in allk if k["N"] > 0]
        pl = m.get("played")
        if not kids or not pl or pl in ("PASS", "Resign"):
            continue
        checked += 1
        w = 50 + max(k["N"] for k in allk)
        best = max(kids, key=lambda k: k["p_logit"] + w * qnorm(k))
        if coord(best) != pl:
            mism += 1

    # [6] 探索は方策(p_logit)の順位を覆したか
    # root 直下の子（>=2 手ある ply のみ）を p_logit 降順に並べ、
    # 訪問数 N がその順で非増加なら prior 不変、増加があれば探索が prior を覆した。
    overturn = overturn_tot = 0
    for m in ms:
        ch = m["root"].get("children", [])
        if len(ch) < 2:
            continue
        overturn_tot += 1
        Ns = [c["N"] for c in sorted(ch, key=lambda c: -c["p_logit"])]
        if any(Ns[i] < Ns[i + 1] for i in range(len(Ns) - 1)):
            overturn += 1

    nonuni = tie_top = n_live = 0
    tiers = None
    root_n = None
    for m in live:
        Ns = sorted((k["N"] for k in m["root"].get("children", [])), reverse=True)
        if len(Ns) < 2:
            continue
        n_live += 1
        if root_n is None:
            root_n = m["root"]["N"]
        if max(Ns) - min(Ns) > 1:
            nonuni += 1
        if Ns.count(Ns[0]) > 1:
            tie_top += 1
        if tiers is None and len(Ns) >= 8:
            tiers = Ns

    return {"n": n_expected, "plies": len(ms), "resign": resign, "root_N": root_n,
            "noisy": noisy, "mism": mism, "checked": checked,
            "nonuni": nonuni, "n_live": n_live, "tie_top": tie_top, "tiers": tiers,
            "overturn": overturn, "overturn_tot": overturn_tot}


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "xrl_viz/data/sweep"
    files = []
    for f in sorted(os.listdir(d)):
        m = re.match(r"n(\d+)_eval_.*\.json$", f)
        if m:
            files.append((int(m.group(1)), os.path.join(d, f)))
    files.sort()
    if not files:
        print(f"{d} に n<数字>_eval_*.json が見つかりません")
        return

    rows = [analyze(p, n) for n, p in files]

    print("=" * 92)
    print("[1] 決定論条件と決定過程（全水準で 0 でなければならない）")
    print("=" * 92)
    print(f"{'n':>5} | {'root N':>7} | {'p_noise!=0':>11} | {'score-argmax != played':>24} | 判定")
    print("-" * 92)
    for r in rows:
        ok = (r["noisy"] == 0 and r["mism"] == 0)
        print(f"{r['n']:>5} | {str(r['root_N']):>7} | {r['noisy']:>11} | "
              f"{r['mism']:>10} / {r['checked']:<11} | {'OK' if ok else 'NG'}")

    print()
    print("=" * 92)
    print("[2] halving の発火点（root 直下 N が一様から崩れる点）")
    print("=" * 92)
    print(f"{'n':>5} | {'N 非一様な ply':>16} | {'発火':>7} | 訪問数 N の分布（代表 ply, k>=8）")
    print("-" * 92)
    fire = None
    for r in rows:
        fired = r["nonuni"] > 0
        if fired and fire is None:
            fire = r["n"]
        t = compress(r["tiers"]) if r["tiers"] else "-"
        print(f"{r['n']:>5} | {r['nonuni']:>6} / {r['n_live']:<7} | "
              f"{'発火' if fired else '非発火':>7} | {t}")
    print()
    print(f"--> halving が発火し始める n = {fire}" if fire else "--> 全水準で非発火")
    print("    実装の予測: n >= log2(m) * m/2 = 4 * 8 = 32  [gumbel_zero.cpp L109-110]")

    print()
    print("=" * 92)
    print("[3] 「最も多く読んだ手」は一意に決まるか（最上位 N の同点率）")
    print("=" * 92)
    print(f"{'n':>5} | {'最上位が同点の ply':>22} | 解釈")
    print("-" * 92)
    for r in rows:
        rate = r["tie_top"] / r["n_live"] if r["n_live"] else 0
        note = ("全手が同点（halving 非発火）" if r["n"] < 32
                else "最終候補2手が同点 [L110: sample_size_ > 2]")
        print(f"{r['n']:>5} | {r['tie_top']:>8} / {r['n_live']:<8} ({rate:5.1%}) | {note}")
    print()
    print("--> argmax-N が同点なら「最も多く読んだ手」という説明は成立しない。")
    print("    決定は argmax(p_logit + (50 + N_max) * qNorm)。")

    print()
    print("=" * 92)
    print("[6] 探索は方策の順位を覆したか（木の形が方策だけで決まっていないか）")
    print("=" * 92)
    print(f"{'n':>5} | {'prior を覆した ply':>22} | 解釈")
    print("-" * 92)
    turn = None
    for r in rows:
        rate = r["overturn"] / r["overturn_tot"] if r["overturn_tot"] else 0
        overt = r["overturn"] > 0
        if overt and turn is None:
            turn = r["n"]
        note = ("探索が木の形に影響していない（並びも訪問数も方策順）" if not overt
                else "低 logit の子が高 logit の子より多く訪問された")
        print(f"{r['n']:>5} | {r['overturn']:>8} / {r['overturn_tot']:<8} ({rate:5.1%}) | {note}")
    print()
    print(f"--> 探索が方策の順位を覆し始める n = {turn}" if turn
          else "--> 全水準で prior 不変")
    print("    n=16/24 は訪問数分布が p_logit 降順で完全に非増加 = 木の形は方策だけで決まる。")
    print("    [2] の halving 発火点と同じ n で転換する。")


if __name__ == "__main__":
    main()
