#!/usr/bin/env python3
"""replay_line.py — 任意の棋譜の着手列を，指定 n のエンジンに打ち直させる．

replay.py は n16 の棋譜専用で，かつ最初の Resign で打ち切る．こちらは
  - 参照する棋譜を引数で選べる
  - 着手列を「連続する盤面の差分」から復元するので Resign 区間も辿れる
という違いがある．

Resign 区間を盤面差分で復元する理由 [事実]:
  console.cpp:170 の think(with_play=true) が着手を打った後で，
  console.cpp:172 の isResign() が真だと応答を "Resign" に差し替える．
  つまり played が "Resign" でも着手は盤面に反映されており，
  played の文字列だけでは着手が分からない．

前提: MiniZero のコンテナ内で実行すること．
使い方:
  python3 xrl_viz/replay_line.py SRC.json MAX_PLY N OUT.json [BIN]
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "xrl_viz"))
from check_alignment import legal_moves  # noqa: E402

MODEL = "othello_8x8_gaz_n16/model/weight_iter_150000.pt"


def coord(r, c):
    return f"{chr(ord('A') + c + (1 if c >= 8 else 0))}{r + 1}"


def recover_line(moves, bsize, max_ply):
    """(ply, color, move) の列を盤面差分から復元する．move は座標か "PASS"．"""
    line = []
    for i in range(len(moves) - 1):
        m, nxt = moves[i], moves[i + 1]
        if m["ply"] > max_ply:
            break
        cur, nb = m["board"], nxt["board"]
        newly = [(r, c) for r in range(bsize) for c in range(bsize)
                 if cur[r][c] is None and nb[r][c] is not None]
        legal = {(r, c) for r, c in legal_moves(cur, m["to_play"], bsize)}
        if len(newly) == 1:
            if newly[0] not in legal:
                sys.exit(f"ply {m['ply']}: 復元した着手 {coord(*newly[0])} が合法手でない")
            line.append((m["ply"], m["to_play"], coord(*newly[0])))
        elif len(newly) == 0:
            if legal:
                sys.exit(f"ply {m['ply']}: 石が置かれていないのに合法手が {len(legal)} ある")
            line.append((m["ply"], m["to_play"], "PASS"))
        else:
            sys.exit(f"ply {m['ply']}: 新たに置かれた石が {len(newly)} 個あり着手を特定できない")
    return line


def run(line, n, binary):
    cmds = ["clear_board"]
    for _, color, move in line:
        c = color.lower()
        cmds += [f"reg_genmove {c}", "tree_json", f"play {c} {move}"]
    cmds.append("quit")
    cfg = f"xrl_viz/cfg/othello_8x8_gaz_eval_n{n}.cfg"
    inner = (f"cd {REPO} && {binary} -mode console -conf_file {cfg} "
             f"-conf_str nn_file_name={MODEL} 2>/dev/null")
    p = subprocess.run(["bash", "-lc", inner], input="\n".join(cmds) + "\n",
                       capture_output=True, text=True, timeout=3600)
    bodies = [ln[2:].strip() for ln in p.stdout.splitlines() if ln.startswith("= ")]
    if not bodies:
        sys.exit("応答なし（コンテナ内で実行しているか確認）")
    expected = 1 + 3 * len(line)
    if len(bodies) != expected:
        sys.exit(f"応答数が {len(bodies)}，期待 {expected}．出力が欠落している")
    out, idx = [], 1
    for (ply, color, move) in line:
        reg_move, tj = bodies[idx], bodies[idx + 1]
        idx += 3
        if not tj.startswith("{"):
            sys.exit(f"ply {ply}: tree_json が JSON でない")
        out.append({"ply": ply, "color": color, "line_move": move,
                    "engine_move": reg_move, "tree": json.loads(tj)})
    return out


if __name__ == "__main__":
    src, max_ply, n, outp = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    binary = sys.argv[5] if len(sys.argv) > 5 else "build/othello/minizero_othello"
    d = json.load(open(os.path.join(REPO, src)))
    line = recover_line(d["moves"], d["board_size"], max_ply)
    res = run(line, n, binary)
    with open(os.path.join(REPO, outp), "w") as f:
        json.dump(res, f)
    same = sum(1 for r in res if r["engine_move"].upper() == r["line_move"].upper())
    print(f"n={n}: {len(res)} ply -> {outp}  (棋譜と同着手 {same}/{len(res)})")
