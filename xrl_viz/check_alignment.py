#!/usr/bin/env python3
"""check_alignment.py — Capture_game.sh 出力の健全性を検査する。

検査項目:
  1. tree 件数と ply 数の整合（最も確実な検査なので最初に置く）
  2. played の座標が root の子に存在するか
  3. played の位置が board 上で空か
  4. PASS の ply で本当に合法手がゼロだったか
  5. 合法手数 k の分布（k > actor_gumbel_sample_size の ply がどれだけあるか）

座標変換の根拠 [事実]:
  sgf_loader.cpp L101-111 … x = aid % bsize, y = aid // bsize,
  文字 = 'A' + x + (x >= 8), 数字 = y + 1, PASS は aid == bsize*bsize。
  console.cpp boardToJson … board[row][col] は index row*bsize+col、
  row 0 が rank 1、空マスは JSON の null。

使い方: python3 xrl_viz/check_alignment.py [--m 16] FILE.json [FILE.json ...]
"""
import json
import sys

DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def aid_to_coord(aid, bsize):
    if aid is None or aid < 0 or aid >= bsize * bsize:
        return None
    x, y = aid % bsize, aid // bsize
    return f"{chr(ord('A') + x + (1 if x >= 8 else 0))}{y + 1}"


def coord_to_rc(coord, bsize):
    """'E3' -> (row, col) = (2, 4)。'I' 飛ばしの逆変換も行う。"""
    letter, num = coord[0], int(coord[1:])
    x = ord(letter) - ord("A")
    if letter > "I":
        x -= 1
    return num - 1, x


def legal_moves(board, player, bsize):
    """board[row][col] は 'B'/'W' 相当の文字か None。player は着手側の文字。"""
    opp = "W" if player == "B" else "B"
    out = set()
    for r in range(bsize):
        for c in range(bsize):
            if board[r][c] is not None:
                continue
            for dr, dc in DIRS:
                rr, cc, seen = r + dr, c + dc, 0
                while 0 <= rr < bsize and 0 <= cc < bsize and board[rr][cc] == opp:
                    rr += dr
                    cc += dc
                    seen += 1
                if seen and 0 <= rr < bsize and 0 <= cc < bsize and board[rr][cc] == player:
                    out.add((r, c))
                    break
    return out


def check(path, m):
    d = json.load(open(path))
    bsize = d["board_size"]
    moves = d["moves"]
    expected = 64  # gen_cmds は tree_json を 1 + MAX 回発行する（MAX=64）
    print(f"{path}")
    print(f"  [1] ply 数 {len(moves)}"
          + ("" if len(moves) == expected else f"  ← 期待 {expected} と不一致（tree_json が欠落した疑い）"))

    n_ok = n_not_child = n_occupied = n_pass_ok = n_pass_bad = n_resign = 0
    bad = []
    k_hist = []
    for mv in moves:
        played, board, to_play = mv["played"], mv["board"], mv["to_play"]
        legal = legal_moves(board, to_play, bsize)
        k_hist.append(len(legal))
        if played == "Resign":
            n_resign += 1
            continue
        if played == "PASS":
            if legal:
                n_pass_bad += 1
                bad.append((mv["ply"], "PASS", f"合法手が {len(legal)} 個あるのに PASS"))
            else:
                n_pass_ok += 1
            continue
        kids = {aid_to_coord(c["action_id"], bsize) for c in mv["root"].get("children", [])}
        r, c = coord_to_rc(played, bsize)
        if played not in kids:
            n_not_child += 1
            bad.append((mv["ply"], played, "root の子に無い"))
        elif board[r][c] is not None:
            n_occupied += 1
            bad.append((mv["ply"], played, f"board が空でない({board[r][c]!r})"))
        else:
            n_ok += 1

    print(f"  [2][3] 通常手 整合 {n_ok} / root に無い {n_not_child} / 空でない {n_occupied}")
    print(f"  [4] PASS 正当 {n_pass_ok} / PASS 不当 {n_pass_bad} / Resign {n_resign}")
    over = [k for k in k_hist if k > m]
    print(f"  [5] 合法手数 k: 最大 {max(k_hist)} / 平均 {sum(k_hist) / len(k_hist):.1f}"
          f" / k > m(={m}) の ply {len(over)}/{len(k_hist)}")
    if bad:
        print(f"      最初の不整合: {bad[:6]}")
    return n_not_child + n_occupied + n_pass_bad + (len(moves) != expected)


if __name__ == "__main__":
    argv = sys.argv[1:]
    m = 16
    if "--m" in argv:
        i = argv.index("--m")
        m = int(argv[i + 1])
        del argv[i:i + 2]
    bad = 0
    for p in argv:
        bad += check(p, m)
    sys.exit(1 if bad else 0)
