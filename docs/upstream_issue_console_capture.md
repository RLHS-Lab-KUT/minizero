# upstream issue 草案（2件目・材料のみ）— コンソール出力の混線と黙殺スキップ

提出先：rlglab/minizero
状態：**未提出．VL バグの issue（`upstream_issue_gumbel_virtual_loss.md`）が
片付いてから出す．** 1件目と混ぜない．

これは Task 1 の virtual loss バグとは**独立した別件**．探索の正しさではなく，
コンソールモードの出力が機械可読でないという問題．

---

## 症状 [事実]

`tools/quick-run.sh console` 経由でコンソールを動かすと，GTP 応答を書く stdout に
色付けされた盤面表示が割り込み，1行の応答が途中で切れる．

実測（othello 8x8，`tree_json` を 65 回発行）：

| 経路 | stdout の制御文字 | パースできた tree_json |
|------|------------------|----------------------|
| `tools/quick-run.sh console` 経由 | 1113 個 | **48 / 64** |
| `build/othello/minizero_othello` 直接 | 0 個 | **65 / 65** |

## 機構 [事実]

- `minizero/console/console.cpp:170` が `actor_->think(..., display_board = true)` を呼ぶ
- `minizero/actor/zero_actor.cpp:48` が盤面と探索情報を `std::cerr` に出す
- `tools/quick-run.sh:634` が console の stderr を**非同期プロセス置換**で色付けする

```bash
} 2> >(colorize OUT_CONSOLE_ERR >&2)
```

プロセス置換は本体と非同期に走るため，色付けされた盤面表示が stdout の応答行の
途中に入り込む．割り込む位置は実行ごとに変わるので，同じコマンド列を流しても
出力が再現しない．探索そのものは決定論的（着手列は 64/64 一致）で，壊れるのは
出力だけである．

## 影響

コンソールモードの出力を機械可読な入力として使う用途すべて．
GTP クライアント，棋譜収集，探索木のダンプなど．

## 提案する修正（案）

- console の応答（stdout）とログ・盤面表示（stderr）を混ぜない
- 少なくとも，色付けを同期的に行うか，`-t` 相当の判定で応答側には一切触れない
- `display_board` を console 側で切れるようにする

---

## 併せて報告する別の欠陥（こちらの fork 側の話だが同種）

`xrl_viz/Capture_game.sh` は壊れた行を
`except json.JSONDecodeError: continue` で黙って捨てていた．その結果
`trees[]` が縮み，board と root の対応が 1 ply ずれ，
「着手が自分自身の探索 root の子に存在しない」記録が生成される．
**壊れたデータが黙って通るのが最も危険**という例として，本文に含めるか検討する．

fork 側では `f60cb87` で修正済み（直接起動＋応答が壊れていたらエラー終了）．

---

## 確認済みの範囲 [事実]

この不具合による欠落は，既存コーパスには**1件も無い**．
`xrl_viz/check_alignment.py` で全件検査した結果：

| ファイル | ply | 不整合 |
|---|---|---|
| `data/sweep/n{16,24,32,64,128,256}_eval_20260713_game01.json` | 各 64 | 0 |
| `data/baseline/n16_postfix_eval_20260713_game01.json` | 64 | 0 |
| `data/replay_n{16,32,128}.json` | 各 48 | 0 |

`replay.py` はもともとバイナリを直接起動していた（`replay.py` の `BIN`）ため
影響を受けない．`Capture_game.sh` 系も 2026-07-13 の取得時には壊れていなかった．
