#!/usr/bin/env bash
# capture_game.sh — 1局を自己対戦させ、各手番の探索木を1つの moves[] JSON にまとめる。
#
# 重要: MiniZero のコンテナの中で実行すること。
#   1) scripts/start-container.sh   # 対話的にコンテナへ入る
#   2) xrl_viz/capture_game.sh othello_8x8_gaz_n16 > xrl_viz/game.json
#
# コマンド順:
#   先頭で tree_json(初期局面=着手前)を1回。以後、各手番で genmove → tree_json。
#   先頭の tree_json により「初期局面の盤面」をエンジンから直接取得する(ハードコードしない)。
#
# 半手ずれの補正:
#   genmove 直後の tree_json は「着手後の board」だが「着手を選んだ探索の root」を持つ。
#   そこで各 entry の board は「1つ前の tree_json の board」(= その手を指す前の局面)を充て、
#   root は今の tree_json のものにして、board と root の手番を一致させる。

set -euo pipefail

MODEL="${1:?model folder or .pt path required}"
CONF=""
if [[ "${2:-}" == *.cfg ]]; then CONF="$2"; shift; fi
MAX="${2:-64}"
GAME_TYPE="othello"

gen_cmds() {
  echo "tree_json"                 # 初期局面(着手前)の盤面をエンジンから取得
  for ((i=0;i<MAX;i++)); do
    if (( i % 2 == 0 )); then col="b"; else col="w"; fi
    echo "genmove $col"
    echo "tree_json"
  done
  echo "quit"
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
echo "[capture_game] playing one game (max $MAX plies)..." 1>&2
gen_cmds | tools/quick-run.sh console "$GAME_TYPE" "$MODEL" $CONF 2>/dev/null > "$TMP"

python3 - "$TMP" <<'PY'
import sys, json

with open(sys.argv[1]) as f:
    lines = [ln[2:].strip() for ln in f if ln.startswith("= ")]

# 応答列を解析。先頭の tree_json は初期局面(played 無し)。
# 以降は genmove(着手) と tree_json が交互。
trees = []          # tree_json オブジェクトの列(時系列)
played_seq = []     # genmove の着手の列
game = bsize = None
for body in lines:
    if body.startswith("{"):
        try:
            obj = json.loads(body)
        except json.JSONDecodeError:
            continue
        if game is None:
            game = obj.get("game"); bsize = obj.get("board_size")
        trees.append(obj)
    else:
        played_seq.append(body)

# trees[0] = 初期局面の盤面(着手前)。
# trees[k] (k>=1) = k手目の着手後の盤面 + k手目を選んだ探索 root。
# k手目(played_seq[k-1])の entry:
#   board = trees[k-1].board (= その手を指す前の局面)
#   root  = trees[k].root    (= その手を選んだ探索)
moves = []
for k in range(1, len(trees)):
    root = trees[k]["root"]
    to_play = root["children"][0]["player"] if root.get("children") else trees[k].get("to_play")
    moves.append({
        "ply": k - 1,
        "played": played_seq[k-1] if k-1 < len(played_seq) else None,
        "to_play": to_play,
        "board": trees[k-1]["board"],     # 指す前の局面(エンジンの実値)
        "root": root,
    })

out = {"game": game, "board_size": bsize, "moves": moves}
print(json.dumps(out))
sys.stderr.write(f"[capture_game] collected {len(moves)} plies\n")
PY