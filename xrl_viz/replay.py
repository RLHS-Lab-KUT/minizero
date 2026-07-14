#!/usr/bin/env python3
"""n16 の棋譜の各局面を、指定 n のエンジンに reg_genmove で打ち直させて
判断(着手)と探索木を取得する。着手は棋譜(n16)通りに play で強制するため、
n16 と全く同じ局面列を、探索設定 n だけ変えて評価できる。

前提: MiniZero のコンテナ(libtorch入り)の中で実行すること。
  例) docker exec <container> bash -lc 'cd /workspace && python3 xrl_viz/replay.py 128'
出力: xrl_viz/data/replay_n<N>.json  (各 ply: n16着手 / エンジンの着手 / 探索木)

決定論条件(eval cfg: gumbel_noise=false, dirichlet=false, rotation=false)のもとで
完全に再現可能。n16 局面を n16 エンジンに流すと元の着手を 48/48 再現する(自己検証)。
"""
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "othello_8x8_gaz_n16/model/weight_iter_150000.pt"
N16_EVAL = "xrl_viz/data/sweep/n16_eval_20260713_game01.json"
OUTDIR = "xrl_viz/data"
BIN = "build/othello/minizero_othello"


def n16_line():
    """n16 棋譜の投了前の (ply, color, move) 列を返す。"""
    ms = json.load(open(os.path.join(REPO, N16_EVAL)))["moves"]
    resign = next((m["ply"] for m in ms if m.get("played") == "Resign"), None)
    line = []
    for m in ms:
        if resign is not None and m["ply"] >= resign:
            break
        line.append((m["ply"], m["to_play"], m["played"]))
    return line


def build_commands(line):
    cmds = ["clear_board"]
    for _, color, move in line:
        c = color.lower()
        cmds.append(f"reg_genmove {c}")   # 着手せず探索
        cmds.append("tree_json")          # 探索木を取得
        cmds.append(f"play {c} {move}")   # 棋譜(n16)通りに局面を進める
    cmds.append("quit")
    return cmds


def run(n):
    line = n16_line()
    cfg = f"xrl_viz/cfg/othello_8x8_gaz_eval_n{n}.cfg"
    stdin = "\n".join(build_commands(line)) + "\n"
    inner = (f"cd {REPO} && {BIN} -mode console -conf_file {cfg} "
             f"-conf_str nn_file_name={MODEL} 2>/dev/null")
    p = subprocess.run(["bash", "-lc", inner], input=stdin,
                       capture_output=True, text=True, timeout=1800)
    bodies = [ln[2:].strip() for ln in p.stdout.splitlines() if ln.startswith("= ")]
    assert bodies, f"n{n}: 応答なし (コンテナ内で実行しているか確認)"
    idx = 1  # clear_board の空応答を飛ばす
    out = []
    for (ply, color, move) in line:
        reg_move = bodies[idx]
        tj = bodies[idx + 1]
        idx += 3  # reg_move, tree_json, play(空)
        out.append({"ply": ply, "color": color, "n16_move": move,
                    "engine_move": reg_move,
                    "tree": json.loads(tj) if tj.startswith("{") else None})
    return out


if __name__ == "__main__":
    n = int(sys.argv[1])
    res = run(n)
    outpath = os.path.join(REPO, OUTDIR, f"replay_n{n}.json")
    with open(outpath, "w") as f:
        json.dump(res, f)
    same = sum(1 for r in res if r["engine_move"].upper() == r["n16_move"].upper())
    print(f"n={n}: {len(res)} plies -> {outpath}  (n16と同着手 {same}/{len(res)})")
