#!/usr/bin/env python3
"""(II) 14 軌道コーパスの一覧と健全性検査。

14 軌道（src_S{1..4}_n128.json の 4 本と line_<着手列>_n128.json の 10 本）が
1 つのディレクトリに揃っている構成を対象とする。line_* が data/corpus14/、
src_S* が data/corpus/ に分かれていた旧レイアウトには対応しない。
カテゴライズや解釈は書かない。データが揃ったことの確認まで。

使い方: python3 xrl_viz/audit_corpus14.py [コーパスのディレクトリ]
        ディレクトリを省略すると xrl_viz/data/corpus_qt を見る。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_alignment import legal_moves          # noqa: E402
from analyze_taskB_detail import apply_move      # noqa: E402
from audit_corpus import (coord, rc, walk_nodes, line_from_capture,  # noqa: E402
                          final_board, board_str)

B = 8
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DIR = "xrl_viz/data/corpus_qt"

# 14 軌道。4 本は src_S*、残り 10 本は line_*。ディレクトリは引数で与える。
LINES = [
    ("E3 D3 C2", "line_E3D3C2_n128.json"),
    ("E3 D3 C3", "line_E3D3C3_n128.json"),
    ("E3 D3 C4", "src_S1_n128.json"),
    ("E3 D3 C5", "line_E3D3C5_n128.json"),
    ("E3 D3 C6", "src_S4_n128.json"),
    ("E3 F3 G3", "line_E3F3G3_n128.json"),
    ("E3 F3 F4", "src_S2_n128.json"),
    ("E3 F3 C5", "line_E3F3C5_n128.json"),
    ("E3 F3 D6", "line_E3F3D6_n128.json"),
    ("E3 F5 C6", "line_E3F5C6_n128.json"),
    ("E3 F5 D6", "src_S3_n128.json"),
    ("E3 F5 E6", "line_E3F5E6_n128.json"),
    ("E3 F5 F6", "line_E3F5F6_n128.json"),
    ("E3 F5 G6", "line_E3F5G6_n128.json"),
]


def start():
    b = [[None] * B for _ in range(B)]
    b[3][3] = "B"
    b[3][4] = "W"
    b[4][3] = "W"
    b[4][4] = "B"
    return b


def cell_to_rc(s):
    return int(s[1:]) - 1, ord(s[0].upper()) - ord("A")


def expected_board(moves):
    """開きを打った後の盤面と手番。違法手があれば例外。"""
    b, p = start(), "B"
    for mv in moves:
        r, c = cell_to_rc(mv)
        if (r, c) not in set(legal_moves(b, p, B)):
            raise SystemExit(f"違法手 {mv}（{p}番）")
        b = apply_move(b, p, r * B + c, B)
        p = "W" if p == "B" else "B"
    return b, p


def main():
    argv = sys.argv[1:]
    if len(argv) > 1:
        raise SystemExit(f"引数はコーパスのディレクトリ 1 つだけ。渡された引数: {argv}")
    corpus_dir = argv[0] if argv else DEFAULT_DIR
    # 絶対パスを渡された場合は os.path.join がそちらを優先するので分岐は要らない。
    if not os.path.isdir(os.path.join(ROOT, corpus_dir)):
        raise SystemExit(f"ディレクトリが無い: {corpus_dir}")
    # 14 軌道が 1 ディレクトリに揃っている前提なので ENGINE_COMMIT.txt も 1 つ。
    p = os.path.join(ROOT, corpus_dir, "ENGINE_COMMIT.txt")
    print(f"コーパス: {corpus_dir}")
    print("エンジンのコミット: "
          + (open(p).read().strip() if os.path.exists(p) else "(記録なし)"))
    print()

    lines = [(line, os.path.join(corpus_dir, name)) for line, name in LINES]

    # ---- 開きの到達局面の照合 ----
    print("=== (a) 各開きが全手合法で意図した局面に到達するか ===")
    ng = 0
    for line, rel in lines:
        d = json.load(open(os.path.join(ROOT, rel)))
        rec = [o["move"] for o in d["opening"]]
        eb, ep = expected_board(line.split())
        m0 = d["moves"][0]
        ok_seq = rec == line.split()
        ok_brd = m0["board"] == eb
        ok_ply = m0["ply"] == 3 and m0["to_play"] == ep
        if not (ok_seq and ok_brd and ok_ply):
            ng += 1
        print(f"  {line:10s} 記録の opening {' '.join(rec):10s} 一致 {'Y' if ok_seq else 'N'}"
              f" / moves[0].board が期待盤面と一致 {'Y' if ok_brd else 'N'}"
              f" / ply {m0['ply']} 手番 {m0['to_play']} {'Y' if ok_ply else 'N'}")
    print(f"  NG {ng} 件")

    # ---- 健全性 ----
    print()
    print("=== (b) ply 数・tree_json の欠損・決定論条件 ===")
    print(f"  {'着手列':10s} {'ply数':>6s} {'root欠損':>8s} {'子0のroot':>10s} "
          f"{'終局後':>7s} {'不整合':>7s}  p_noise")
    noise_all = set()
    for line, rel in lines:
        d = json.load(open(os.path.join(ROOT, rel)))
        ms = d["moves"]
        missing = sum(1 for m in ms if not m.get("root"))
        term = bad = nokid = 0
        for m in ms:
            if len(legal_moves(m["board"], m["to_play"], B)) == 0:
                term += 1
                continue
            if not m["root"].get("children"):
                nokid += 1
            if m["played"] in ("Resign", "PASS"):
                continue
            kids = {coord(c["action_id"]) for c in m["root"].get("children", [])}
            r_, c_ = rc(m["played"])
            if m["played"] not in kids or m["board"][r_][c_] is not None:
                bad += 1
        vals = {n.get("p_noise") for m in ms for n in walk_nodes(m["root"])}
        noise_all |= vals
        print(f"  {line:10s} {len(ms):6d} {missing:8d} {nokid:10d} {term:7d} {bad:7d}  {vals}")
    print(f"  全記録の p_noise の値集合: {noise_all}")

    # ---- 一覧 ----
    print()
    print("=== (c) 終局までの手数・最終石差 ===")
    print(f"  {'着手列':10s} {'記録ply':>7s} {'着手数':>6s} {'PASS':>5s} "
          f"{'黒':>4s} {'白':>4s} {'石差(黒-白)':>11s} {'空':>4s} {'結果':>6s}  ファイル")
    boards = {}
    for line, rel in lines:
        d = json.load(open(os.path.join(ROOT, rel)))
        seq = line_from_capture(d)
        fb = final_board(d["initial_board"], seq)
        nb = sum(r.count("B") for r in fb)
        nw = sum(r.count("W") for r in fb)
        npass = sum(1 for _, m in seq if m == "PASS")
        nmv = sum(1 for _, m in seq if m != "PASS")
        empty = 64 - nb - nw
        res = "黒勝ち" if nb > nw else ("白勝ち" if nw > nb else "引分")
        boards[line] = fb
        print(f"  {line:10s} {len(d['moves']):7d} {nmv:6d} {npass:5d} {nb:4d} {nw:4d} "
              f"{nb - nw:11d} {empty:4d} {res:>6s}  {rel}")

    print()
    print("=== (d) 最終盤面 ===")
    for line, _ in LINES:
        print(f"\n  [{line}]")
        print(board_str(boards[line]))

    print()
    print("=== (e) 到達局面の重複 ===")
    seen = {}
    for line, _ in LINES:
        key = tuple(tuple(r) for r in boards[line])
        if key in seen:
            print(f"  {line} の最終盤面は {seen[key]} と同一")
        seen[key] = line
    print(f"  相異なる最終盤面 {len(seen)} / {len(LINES)}")


if __name__ == "__main__":
    main()
