#!/usr/bin/env bash
# capture_levels.sh — n = 16 / 32 / 128 の3水準で決定論 eval 記録を取得する。
# sweep_n.sh との違い: 出力先とファイル接頭辞を引数で指定でき、同一局面の
# 「修正前 / 修正後」を並べて保存するために使う。
#
# 使い方（コンテナ内で実行）:
#   xrl_viz/capture_levels.sh OUTDIR PREFIX
#   例) xrl_viz/capture_levels.sh xrl_viz/data/pre_vlfix preinstr
#       -> xrl_viz/data/pre_vlfix/preinstr_n16.json など
#
# 出典: halving 発火条件 next_budget = floor(n / (log2(m) * m / 2)) > 0
#       ⇔ n >= 32  [gumbel_zero.cpp L109-110], m = actor_gumbel_sample_size = 16
set -euo pipefail
cd "$(dirname "$0")/.."

OUTDIR="${1:?OUTDIR required}"
PREFIX="${2:?PREFIX required}"

MODEL="othello_8x8_gaz_n16/model/weight_iter_150000.pt"
MAX_MOVES=64
LEVELS=(16 32 128)

mkdir -p "$OUTDIR"

for n in "${LEVELS[@]}"; do
  CFG="xrl_viz/cfg/othello_8x8_gaz_eval_n${n}.cfg"
  [ -e "$CFG" ] || { echo "NG: $CFG が無い"; exit 1; }

  # 決定論性の前提をここで固定する。1つでも崩れると修正前後の比較が成立しない。
  for kv in "actor_num_simulation=${n}" \
            "actor_use_gumbel=true" \
            "actor_use_gumbel_noise=false" \
            "actor_use_dirichlet_noise=false" \
            "actor_use_random_rotation_features=false" \
            "actor_select_action_by_count=true" \
            "actor_select_action_by_softmax_count=false" \
            "actor_mcts_think_batch_size=1" \
            "actor_gumbel_sample_size=16"; do
    grep -qE "^${kv}( |$|#)" "$CFG" || { echo "NG $CFG: $kv が満たされていない"; exit 1; }
  done

  OUT="${OUTDIR}/${PREFIX}_n${n}.json"
  echo "==> n=${n} -> ${OUT}"
  xrl_viz/Capture_game.sh "$MODEL" "$CFG" "$MAX_MOVES" > "$OUT"
  echo "    完了 ($(python3 -c "import json;print(len(json.load(open('$OUT'))['moves']))") ply)"
done
