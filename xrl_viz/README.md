# xrl_viz — 探索木の可視化と解析

MCTS の探索木（tree_json）を撮って，読んで，図にするための一式．

## スクリプトと Gumbel 依存

学習・評価に使ったモデルは Gumbel AlphaZero（`actor_use_gumbel=true`）である．
AlphaZero（`actor_use_gumbel=false`）に切り替えた場合，下表の「依存」が
`直接` または `cfg 経由` のものはそのままでは使えない．

| スクリプト | 依存 | 根拠（行番号） |
|---|---|---|
| `analyze_initial.py` | **直接** | `gaz_decision_score` / `gaz_eliminated_round` を読む（:16, :37） |
| `analyze_symmetry.py` | **直接** | 同上（:29, :136-137） |
| `gen_corpus14.sh` | **cfg 経由** | `cfg/othello_8x8_gaz_eval_n128.cfg` を固定指定（:14） |
| `sweep_n.sh` | **cfg 経由** | `BASE_CFG`（:8）を読み，`actor_gumbel_sample_size` / `actor_use_gumbel_noise` を必須検査（:20-25） |
| `audit_corpus14.py` | なし | 読むのは `p_noise` / `board` / ply 数のみ（:95-119） |
| `capture_initial.sh` | なし | cfg は引数（`$2` → `CONF`, :19） |
| `dump_position.py` | なし | `root.children[].N` のみ（:95-96） |
| `make_board_reference.py` | なし | `board` のみ．`gaz_decision_score` は本文中の案内で言及するだけ（:166） |
| `plot_visits_bar.py` | なし | `N` のみ（:75-77） |
| `verify_openings.py` | なし | エンジンを起動しない純 Python の検査 |

補足（tree_json 側の Gumbel 固有の事情，`minizero/console/console.cpp`）:

- `gaz_eliminated_round` / `gaz_decision_score` は**深さ 1（ルート直下）のノードにしか出ない**．
  深さ 2 以上は `-99` 番兵のため `null` になる（`console.cpp:284-299`）．
- **ルートだけ訪問 0 の手も出力される**．Gumbel の top-m 抽出で落ちた手を残すためで，
  非ルートは `count > 0` の子だけに絞られる（`console.cpp:305-311`, `mcts.h:28`）．
- `Q` は `getMean()`（`console.cpp:277`）であって `getNormalizedMean()` ではない．
  手番による符号反転が入っていないので，比較するときは `player` を見て符号を合わせること．

## cfg

| ファイル | `actor_num_simulation` | 用途 |
|---|---|---|
| `othello_8x8_gaz_eval.cfg` | 16 | **テンプレート**．`sweep_n.sh` が `BASE_CFG` として読み，`sed` で n を書き換えて下の 6 件を生成する．`*.cfg` により **gitignore されているので追跡外** |
| `cfg/othello_8x8_gaz_eval_n16.cfg` | 16 | n スイープ．学習時と同じ n |
| `cfg/othello_8x8_gaz_eval_n24.cfg` | 24 | n スイープ |
| `cfg/othello_8x8_gaz_eval_n32.cfg` | 32 | n スイープ．halving 発火条件 `n >= log2(m) * m/2 = 32` の境界（`gumbel_zero.cpp:109-110`） |
| `cfg/othello_8x8_gaz_eval_n64.cfg` | 64 | n スイープ |
| `cfg/othello_8x8_gaz_eval_n128.cfg` | 128 | n スイープ．コーパス生成の既定 |
| `cfg/othello_8x8_gaz_eval_n256.cfg` | 256 | n スイープ |

- `cfg/` の 6 件は相互に `actor_num_simulation` の 1 行しか違わない．
- `othello_8x8_gaz_eval.cfg` は `cfg/othello_8x8_gaz_eval_n16.cfg` と md5 一致
  （`bf0a6dc6ac6b78b6899ea59fcdb4715f`）．テンプレートの既定 n が 16 のため．
  **古い残骸ではなく現役**だが追跡外なので，クローンした状態から `sweep_n.sh` を
  走らせるにはこのファイルを別途用意するか，`cfg/` の 6 件をそのまま使うこと．
- 学習時 cfg（`othello_8x8_gaz_n16/othello_8x8_gaz_n16.cfg`，これも追跡外）との差は
  `actor_num_simulation` に加えて次の 4 点:
  `actor_select_action_by_count=true` / `actor_select_action_by_softmax_count=false` /
  `actor_use_gumbel_noise=false` / `actor_use_random_rotation_features=false`

## data/

**`data/**/*.json` は `.gitignore` で追跡外**（tree_json は 1 記録あたり 1.5 MB 前後）．
追跡しているのはメタ情報・分析結果・図の入力だけ．
`data/**/*.log` も追跡外（進捗表示 2 行のみで再現情報を持たない）．
上の 1.5 MB は `q_trace` を持たない記録（`data/corpus/` `data/corpus14/`）の値である．
`q_trace` を含む記録（`data/corpus_qt/`）では 1 記録あたり約 2.4 MB になる．

### `data/corpus14/` — 初手 E3 の対称正規化 3 手開き 14 軌道（n=128）

| ファイル | 追跡 | 内容 |
|---|---|---|
| `line_<着手列>_n128.json` 10 件 | **追跡外**（計 15.0 MB） | 新規に撮った 10 軌道 |
| `line_<着手列>_n128.log` 10 件 | **追跡外** | 取得時の進捗 2 行 |
| `ENGINE.txt` | 追跡 | 生成に使ったバイナリの md5 / mtime / 自己申告版 / 生成時のリポジトリ HEAD |
| `audit_report.txt` | 追跡 | 14 軌道の合法性・到達局面一致・ply 数・欠損・決定論条件の判定 |

残り 4 軌道は `data/corpus/src_S{1..4}_n128.json`（同一バイナリで 2026-07-21 生成，追跡外）．
生成: `gen_corpus14.sh` / 検査: `audit_corpus14.py`

### `data/corpus_qt/` — 上記 2 つの 29 記録を `q_trace` 付きで撮り直したもの（n=16/32/128）

| ファイル | 追跡 | 内容 |
|---|---|---|
| `src_S{1..4}_n128.json` 4 件 | **追跡外**（計 9.0 MB） | 4 系統を n=128 で対局させた源泉 |
| `replay_S{1..4}_n{16,32,128}.json` 12 件 | **追跡外**（計 13.1 MB） | 源泉の着手列を 3 水準に打ち直したもの |
| `indep_S1_n{16,32,128}.json` 3 件 | **追跡外**（計 3.1 MB） | 系統 S1 を 3 水準で独立に対局させたもの |
| `line_<着手列>_n128.json` 10 件 | **追跡外**（計 22.6 MB） | 対称正規化 3 手開きの残り 10 軌道 |
| `line_<着手列>_n128.log` 10 件 | **追跡外** | 取得時の進捗 2 行 |
| `ENGINE_COMMIT.txt` | 追跡 | 生成時のリポジトリ HEAD（`c6863d5`．`q_trace` を入れたコミット） |
| `ENGINE.txt` | 追跡 | 生成に使ったバイナリの md5 / mtime / 自己申告版，ビルド環境，既存コーパスとの一致検証，`q_trace` の検査結果 |
| `audit_report.txt` | 追跡 | 14 軌道の合法性・到達局面一致・ply 数・欠損・決定論条件の判定（`audit_corpus14.py` の出力） |

`data/corpus/`（19 記録）と `data/corpus14/`（10 記録）と同じ 29 記録を，
`q_trace` を出力するエンジンで撮り直したものである．json 29 件で計 47.9 MB．

`data/corpus14/` は 14 軌道のうち 4 本を `data/corpus/src_S*_n128.json` に依存していたが，
`data/corpus_qt/` は `src_S*` も同じディレクトリに入るため，**14 軌道が 1 ディレクトリで完結する**．

生成は同じ出力先へ 2 つのスクリプトを順に走らせる（コンテナ内で実行）：

```
xrl_viz/gen_corpus.sh   xrl_viz/data/corpus_qt   # 19 記録，実測 46 秒
xrl_viz/gen_corpus14.sh xrl_viz/data/corpus_qt   # 10 記録，実測 32 秒
```

`ENGINE_COMMIT.txt` は両方のスクリプトが書き出すため後者で上書きされるが，
同じ HEAD なので値は変わらない（`gen_corpus.sh:28` / `gen_corpus14.sh:24`）．

検証済み：29 件すべてについて，`q_trace` を除いた内容が `data/corpus/` `data/corpus14/` の
対応するファイルと完全一致する（JSON をパースし `sort_keys=True` で正規化して比較）．
つまり `q_trace` の追加で探索の挙動は変わっていない．

### `data/sym/` — 初期局面と点対称 4 状態

| ファイル | 追跡 | 内容 |
|---|---|---|
| `initial_n128.json` | **追跡外** | 初期局面（0 手）で 1 回だけ探索 |
| `state_diag_n128.json` | **追跡外** | C5 C4 D3 |
| `state_antidiag_n128.json` | **追跡外** | F4 F5 E6 |
| `state_rot180_n128.json` | **追跡外** | D6 E6 F5 |
| `repro_S1_ply3.json` | **追跡外** | E3 D3 C4 の ply3 撮り直し（既存記録との一致確認用） |
| `*.log` 4 件 | **追跡外** | 進捗 2 行 |
| `ENGINE.txt` | 追跡 | `data/corpus14/ENGINE.txt` と同内容 |
| `initial_report.txt` | 追跡 | 初期局面 root 直下 4 手の N/P/Q/v/p_logit/gaz_* をフル桁で並べ，max-min を出したもの |
| `symmetry_report.txt` | 追跡 | 4 状態を E3 フレームへ写した突き合わせ（対応ノード数，ΔP の上位など） |

基準は `E3 D3 C4`（`data/corpus/src_S1_n128.json` の `moves[0]`, ply 3, 白番）．
取得: `capture_initial.sh` / 解析: `analyze_initial.py`, `analyze_symmetry.py`

### `data/BOARD_REFERENCE.txt`（追跡）

盤面の読み方（`X`=黒 / `O`=白 / `.`=空 / `*`=その手番の合法手），
座標と `action_id` の対応，各記録の開始局面図．
参照先が `data/sym` `data/corpus14` `data/corpus` の 3 つにまたがるため，
どれかの下ではなく `data/` 直下に置いてある．
生成: `make_board_reference.py`

### `data/analysis_taskB/`, `data/corpus/`（既存）

`data/corpus/README.md` に序盤固定コーパス（S1〜S4 × n=16/32/128）の設計がある．
csv と README，`ENGINE_COMMIT.txt` のみ追跡で，json は追跡外．

## figs/

`board_S2_ply17.json`（図の入力盤面）のみ追跡．
`visits_n128_S2_ply17.pdf` / `.png` は未追跡だが，`.gitignore` には入れていない
（今後 AlphaZero 版で作り直す図まで一律除外しないため）．
生成: `plot_visits_bar.py`
