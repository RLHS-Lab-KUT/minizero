#!/usr/bin/env bash
# capture_opening.sh — 序盤を固定してから残りをエンジンに打たせ、
# 各手番の探索木を1つの moves[] JSON にまとめる。
#
# Capture_game.sh との違いは序盤の固定だけ。エンジンの起動方法は同じで、
# tools/quick-run.sh を経由せずバイナリを直接叩く（研究メモ §2.1b）。
# quick-run.sh は console の stderr を非同期プロセス置換で色付けするため、
# 色付き盤面表示が stdout の tree_json 行に割り込んで JSON が壊れる。
#
# 使い方（コンテナ内で実行）:
#   xrl_viz/capture_opening.sh MODEL CFG "E3 D3 C4" [MAX_GENMOVE] [ERRFILE] > out.json
#
# ERRFILE を渡すと、エンジンの stderr 全文をそのパスに恒久保存する
# (ディレクトリではなくファイルのパス。親ディレクトリは自動で作る)。
# 省略時は保存しない(従来どおり)。既存の呼び出し元(gen_corpus.sh /
# gen_corpus14.sh)は4引数なので影響を受けない。
#
# 固定手は先手(黒)から交互に割り当てる。上の例なら B=E3, W=D3, B=C4 で、
# 以降 ply 3 (白番) からエンジンが指す。
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:?model folder or .pt path required}"
CONF="${2:?cfg required}"
OPENING="${3:?opening moves required, e.g. \"E3 D3 C4\"}"
MAX="${4:-61}"
ERRFILE="${5:-}"         # stderr の保存先ファイルのパス。空なら保存しない
GAME_TYPE="othello"

read -r -a FIXED <<< "$OPENING"
NFIX=${#FIXED[@]}

gen_cmds() {
  echo "tree_json"                       # [T0] 初期局面(着手前)
  for ((i=0;i<NFIX;i++)); do             # [P]  固定手。応答は空
    if (( i % 2 == 0 )); then c="b"; else c="w"; fi
    echo "play $c ${FIXED[$i]}"
  done
  echo "tree_json"                       # [T1] 固定手を打ち終えた局面
  for ((i=0;i<MAX;i++)); do              # 以降エンジンに打たせる
    if (( (NFIX + i) % 2 == 0 )); then c="b"; else c="w"; fi
    echo "genmove $c"
    echo "tree_json"
  done
  echo "quit"
}

TMP="$(mktemp)"
ERRTMP="$(mktemp)"
trap 'rm -f "$TMP" "$ERRTMP"' EXIT
echo "[capture_opening] opening = $OPENING ($NFIX 手固定), max $MAX plies..." 1>&2

MODEL_PT="$MODEL"
[ -d "$MODEL" ] && MODEL_PT=$(ls -t "$MODEL"/model/*.pt "$MODEL"/*.pt 2>/dev/null | head -n1)
# stderr は捨てずに $ERRTMP へ。先頭に cfg ダンプ全文が入る
# (mode_handler.cpp:129。-conf_str 適用後の値)。以降は "(Version: ...)"、
# genmove ごとの盤面表示・探索情報 (zero_actor.cpp:52)、Spent Time
# (console.cpp:171) が続く。cfg_dump.py 側で "(Version:" で打ち切る。
gen_cmds | "build/${GAME_TYPE}/minizero_${GAME_TYPE}" -mode console \
    -conf_file "$CONF" -conf_str "nn_file_name=${MODEL_PT}" > "$TMP" 2> "$ERRTMP"

# cfg を辞書にする。62 キー無ければ cfg_dump.py 側が非ゼロ終了するので、
# set -e によりここで止まる(黙って進めない)。
CFG_JSON="$(python3 xrl_viz/cfg_dump.py "$ERRTMP")"

# ERRFILE 指定時のみ stderr 全文を恒久保存する。ANSI カラーはそのまま。
if [ -n "$ERRFILE" ]; then
  mkdir -p "$(dirname "$ERRFILE")"
  cp "$ERRTMP" "$ERRFILE"
  echo "[capture_opening] stderr を保存: $ERRFILE ($(wc -c < "$ERRFILE") B)" 1>&2
fi

python3 - "$TMP" "$NFIX" "$MAX" "$OPENING" "$CFG_JSON" <<'PY'
import sys, json

path, nfix, maxmv, opening = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
config = json.loads(sys.argv[5])

# cfg のキー数を再検査する。cfg_dump.py 側でも見ているが、
# 受け渡しの途中で欠けていないことをここでも確かめる(黙って進めない)。
EXPECTED_NUM_PARAMS = 62
if len(config) != EXPECTED_NUM_PARAMS:
    sys.exit(f"[capture_opening] 致命的: cfg のキーが {len(config)} 件、"
             f"期待 {EXPECTED_NUM_PARAMS} 件")
with open(path) as f:
    bodies = [ln[2:].strip() for ln in f if ln.startswith("= ")]

# 応答は位置で読む。件数がずれていたら黙って進めずに落とす。
expected = 1 + nfix + 1 + 2 * maxmv
if len(bodies) != expected:
    sys.exit(f"[capture_opening] 致命的: 応答が {len(bodies)} 件、期待 {expected} 件。欠落している")

def as_tree(i, what):
    b = bodies[i]
    if not b.startswith("{"):
        sys.exit(f"[capture_opening] 致命的: {what} が JSON でない: {b[:120]!r}")
    try:
        return json.loads(b)
    except json.JSONDecodeError as e:
        sys.exit(f"[capture_opening] 致命的: {what} のパースに失敗: {e}")

t0 = as_tree(0, "初期局面の tree_json")
for i in range(1, 1 + nfix):
    if bodies[i] != "":
        sys.exit(f"[capture_opening] 致命的: 固定手 {i} の応答が空でない: {bodies[i]!r}")
t1 = as_tree(1 + nfix, "固定手後の tree_json")

game, bsize = t0.get("game"), t0.get("board_size")
fixed = opening.split()
opening_rec = [{"ply": i, "color": "B" if i % 2 == 0 else "W", "move": m}
               for i, m in enumerate(fixed)]

# 以降 (genmove, tree_json) の対。board は「その手を指す前の局面」を充てるため
# 1つ前の tree のものを使い、root は今の tree のものにする(Capture_game.sh と同じ)。
moves, prev = [], t1
base = 1 + nfix + 1
for k in range(maxmv):
    played = bodies[base + 2 * k]
    tj = as_tree(base + 2 * k + 1, f"{k} 手目の tree_json")
    root = tj["root"]
    to_play = root["children"][0]["player"] if root.get("children") else tj.get("to_play")
    moves.append({"ply": nfix + k, "played": played, "to_play": to_play,
                  "board": prev["board"], "root": root})
    prev = tj

out = {"game": game, "board_size": bsize, "opening": opening_rec,
       "initial_board": t0["board"], "config": config, "moves": moves}
print(json.dumps(out))
sys.stderr.write(f"[capture_opening] collected {len(moves)} plies (ply {nfix}..{nfix+len(moves)-1})\n")
PY
