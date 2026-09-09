#!/usr/bin/env bash
# gen_corpus15_az.sh — 対照モデル(az, 4ch・補助ヘッド無し)で 15 本のコーパスを撮る。
#
# gen_corpus14.sh の az 版。gaz 版は無傷で残してある。gen_corpus14.sh との違い:
#   - MODEL / CFG が az のもの
#   - 既存軌道の再利用をしない。14 本すべてをこのスクリプトで撮る
#     (ファイル名は audit_corpus14.py の LINES に合わせる。4 本は src_S{1..4}、
#      残り 10 本は line_<着手列>。無改修で監査を通すため)
#   - 3 手固定の 14 本に加えて、0 手固定の 1 本(ply 0 から az が自分で指す)を撮る
#   - 出力は 1 ディレクトリに集約し、ENGINE_COMMIT.txt は 15 本を通して 1 回だけ書く
#
# 既存データは壊さない: 出力先に同名の .json が既にあればその 1 本を飛ばす。
# ENGINE_COMMIT.txt も既にあれば書き直さない(15 本を通して 1 回だけ)。
#
# 使い方(コンテナ内で実行): xrl_viz/gen_corpus15_az.sh OUTDIR
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:?出力先ディレクトリが必要（既存を上書きしないよう既定値は置かない）}"
MODEL="othello_8x8_az_n128/model/weight_iter_150000.pt"
CFG="xrl_viz/cfg/othello_8x8_az_eval_n128.cfg"

MAX_FIXED=61          # 3 手固定。3 + 61 = 64 ply 記録(既存 14 本と同じ)
MAX_FREE=64           # 0 手固定。0 + 64 = 64 ply 記録(3 手固定と同じ長さ)
FREE_NAME="free_n128" # 0 手固定の 1 本の出力名

# 3 手固定の 14 系統。tools/opening_branches.py の全列挙。
# ファイル名は audit_corpus14.py の LINES に合わせる。
LINES=(
  "E3 D3 C2|line_E3D3C2_n128"
  "E3 D3 C3|line_E3D3C3_n128"
  "E3 D3 C4|src_S1_n128"
  "E3 D3 C5|line_E3D3C5_n128"
  "E3 D3 C6|src_S4_n128"
  "E3 F3 G3|line_E3F3G3_n128"
  "E3 F3 F4|src_S2_n128"
  "E3 F3 C5|line_E3F3C5_n128"
  "E3 F3 D6|line_E3F3D6_n128"
  "E3 F5 C6|line_E3F5C6_n128"
  "E3 F5 D6|src_S3_n128"
  "E3 F5 E6|line_E3F5E6_n128"
  "E3 F5 F6|line_E3F5F6_n128"
  "E3 F5 G6|line_E3F5G6_n128"
)

mkdir -p "$OUT"
if [ -e "$OUT/ENGINE_COMMIT.txt" ]; then
  echo "[gen_corpus15_az] ENGINE_COMMIT.txt は既にある。書き直さない: $(cat "$OUT/ENGINE_COMMIT.txt")" 1>&2
else
  git log -1 --format='%H' > "$OUT/ENGINE_COMMIT.txt"
  echo "[gen_corpus15_az] エンジンのコミット: $(cat "$OUT/ENGINE_COMMIT.txt")" 1>&2
fi

capture() {  # capture <着手列(空可)> <出力名> <MAX>
  local line="$1" name="$2" max="$3"
  if [ -e "$OUT/${name}.json" ]; then
    echo "=== [skip] ${name}.json は既にある ===" 1>&2
    return 0
  fi
  echo "=== ${name}  opening=\"${line}\"  MAX=${max} ===" 1>&2
  xrl_viz/capture_opening.sh "$MODEL" "$CFG" "$line" "$max" \
      > "$OUT/${name}.json" 2> "$OUT/${name}.log"
}

# 0 手固定の 1 本を先に撮る(所要時間の目安を最初に出すため)。
capture "" "$FREE_NAME" "$MAX_FREE"

for ent in "${LINES[@]}"; do
  capture "${ent%%|*}" "${ent##*|}" "$MAX_FIXED"
done

echo "=== 完了 ===" 1>&2
ls -1 "$OUT" 1>&2
