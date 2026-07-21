# Task B の調査結果（2026-07-21）

対象データ：`xrl_viz/data/sweep_postfix/post_n{16,32,128}.json`（virtual loss 修正後・各 64 ply）
比較に使った修正前後の打ち直し：`xrl_viz/data/vlfix_replay/`
CSV：`xrl_viz/data/analysis_taskB/`
生成スクリプト：`xrl_viz/analyze_taskB.py`, `xrl_viz/analyze_taskB_detail.py`

---

## Step 0：tree_json から「候補にすら入らなかった手」が消える件

### 0-1. 該当箇所 [事実]

```cpp
// minizero/actor/tree.h:39      基底は無条件に出す
    virtual bool displayInTreeLog() const { return true; }

// minizero/actor/mcts.h:28      MCTSNode がこれを上書きして訪問0を落とす
    bool displayInTreeLog() const override { return count_ > 0; }

// minizero/console/console.cpp:306   tree_json の子ループ
        if (!child->displayInTreeLog()) { continue; }   // count>0 のみ(tree_sgf と同基準)

// minizero/actor/tree.h:102     tree_sgf 側も同じ判定を使う
            if (!child->displayInTreeLog()) { continue; }
```

`gaz_eliminated_round = -2`（top-m に入らなかった手）は必ず `count_ == 0` なので，
**この行で丸ごと落ちる**．計装しても記録に残らない．

### 0-2. count_ == 0 の子は -2 の手だけか [事実]

root 直下については **-2 の手だけ**．
全 192 ply（3水準×64）で「合法手のうち木に出ていない数」が
`max(0, k - 16)` と**完全に一致**した（`missing_n{16,32,128}.csv` の `matches_topm_rule` が全行 True）．

| n | 木に出ていない合法手の合計 | 規則と一致 |
|---|---|---|
| 16 | 0 | 全 64 ply |
| 32 | 0 | 全 64 ply |
| 128 | 2（ply 24 と 26 の G2） | 全 64 ply |

つまり top-m に入った候補は全員 1 回以上訪問されており，訪問 0 になるのは
top-m から漏れた手だけ．halving で落ちた手は初期予算の分だけ訪問済みで消えない．

**ただし深さ2以降は話が別** [事実]．展開済みノードは合法手の数だけ子を持つが，
そのほとんどが `count_ == 0` で落ちている（下の 0-3 の倍率がその量）．
「count_==0 は -2 だけ」が言えるのは root 直下に限る．

### 0-3. フィルタを外した場合の増加量

ノード数は**実測**（木を辿りながら盤面を進め，各展開ノードの合法手数を数えた）．
バイト数はノード数に比例すると仮定した概算 [推論]．

| n | 現在のノード数 | フィルタ除去時 | 倍率 | 現サイズ | 概算サイズ |
|---|---|---|---|---|---|
| 16 | 978 | 3,404 | 3.48 | 264 KB | 約 918 KB |
| 32 | 1,832 | 11,509 | 6.28 | 454 KB | 約 2.8 MB |
| 128 | 6,665 | 46,889 | 7.04 | 1.53 MB | 約 10.8 MB |

対して **root 直下だけ全部出す場合の増加は上表の「木に出ていない合法手の合計」そのもの**で，
この3局では合計 2 ノード．費用はほぼゼロ．

### 0-4. 修正案と採用結果

| 案 | 内容 | 増加量 | 説明能力 | GUI への影響 |
|---|---|---|---|---|
| **A** | `displayInTreeLog()` の判定を撤廃 | 3.5〜7 倍 | 全ノードの合法手が見える | 木ペインの描画量が数倍．要調整 |
| **B** | root 直下だけ `count_ == 0` でも出す | ほぼゼロ | 「候補にすら入らなかった手」を特定できる | 訪問0の子が root 直下に増える |
| **C** | root に合法手一覧を別フィールドで持たせる | ほぼゼロ | 同上（ただしノードとしては持たない） | 既存構造を壊さない．無視すれば従来通り |

**案B を採用・適用済み**（`cf20e4c`，`console.cpp` の子ループで `is_root` のときだけ
フィルタを外す）．取り直した記録では n=128 に `-2` が 2 件現れ，
`N == 0` の子はすべて `-2` だった．着手と訪問数分布は取り直し前と変わっていない．

案A は探索木の見え方そのものが変わるため，Phase II の説明設計を決めてからの方が安全 [推論]．

**GUI への影響 [要確認]**：`xrl_viz/index.html` の `drawArgmax`（L272 以降）は
root の全子に `p_logit + (50 + Nmax) * q` を当ててスコア降順に並べる．
一方エンジンは `count == 0` の候補にスコアの下限値を入れる
（`gumbel_zero.cpp` の `node->getCount() > 0 ? score : min_value`）．
案B で N=0 の子が root 直下に出るようになったため，
**GUI 上でその手が本来より上位に並びうる**．実動確認と，必要なら
「N==0 なら最下位に落とす」ガードの追加が要る．

---

## Step 1：§2.3「上位2手の訪問数タイ」の検証

生存手 = `gaz_eliminated_round == -1`（最後まで候補として残った手）．
一次データ：`survivors_n{16,32,128}.csv`．

### 結果 [事実]

| n | 生存手がちょうど2手の ply | 生存2手の N が一致 | 不一致 | **一致率** | 不一致時の差 |
|---|---|---|---|---|---|
| 16 | 1 / 64 | 1 | 0 | — | — |
| 32 | 58 / 64 | 38 | 20 | **38/58 = 65.5%** | **全て 1** |
| 128 | 56 / 64 | 56 | 0 | **56/56 = 100%** | — |

- **n=128 では仮説どおり，生存2手の訪問数が例外なく同数**になる．
- **n=32 では 34.5% の ply で同数にならない**．ただし差は常にちょうど 1．
- n=16 は halving が1巡も走らないため生存手が候補全体（k 手）になり，
  この仮説の適用対象外．「ちょうど2手」になったのは k=2 の 1 ply だけ．
- 生存手が2手でない ply（n=32 で 6，n=128 で 8）は，いずれも終盤で
  合法手が 1 手以下または PASS の局面．

### 「着手が生存手でない」ply について [事実]

n=16 で 8，n=32 で 2，n=128 で 4 件あるが，**全て `played == "Resign"`**．
`console.cpp:172` が探索結果の着手ではなく "Resign" を返すためで，
探索そのものは生存手を選んでいる．実質の例外は 0 件．

### 解釈 [推論]

差が常にちょうど 1 であることから，これは残予算のパリティの問題と考えられる．
最終巡で残った 2 手に残りシミュレーションを交互配分するため，
残予算が偶数なら同数，奇数なら 1 だけずれる．n=128 では割り切れ，n=32 では割り切れない
ply が 3 分の 1 ほどある，という説明で観測と整合する．**未検証**．

### §2.3 への対応

「n をいくら増やしても上位2手の訪問数が同数になる」は，
**n=128 では実測で成立，n=32 では 65.5% でしか成立しない**．
§2.3 を [要確認] から外すかどうかの判断はしていない（docs は未変更）．

---

## Step 2：top-m の選抜は確定的か

### 2-1. 並べ替えに使う値 [事実]

```cpp
// minizero/actor/gumbel_zero.cpp:96
        sort(candidates_.begin(), candidates_.end(), [](const MCTSNode* lhs, const MCTSNode* rhs) { return lhs->getPolicyLogit() > rhs->getPolicyLogit(); });
```

`getPolicyLogit()` の降順．上位 `actor_gumbel_sample_size` 手が候補として残る（L101-104）．

### 2-2. getPolicyLogit は Gumbel ノイズを含むか [事実]

`policy_logit_` に書き込むのは2箇所だけ．

```cpp
// minizero/actor/mcts.cpp:182   展開時にネットワークの生 logit を入れる
        child->setPolicyLogit(candidate.policy_logit_);

// minizero/actor/zero_actor.cpp:210-216   ノイズを足す（この分岐に入ったときだけ）
    } else if (config::actor_use_gumbel_noise) {
        std::vector<float> gumbel_noise = utils::Random::randGumbel(node->getNumChildren());
        for (int i = 0; i < node->getNumChildren(); ++i) {
            MCTSNode* child = node->getChild(i);
            child->setPolicyNoise(gumbel_noise[i]);
            child->setPolicyLogit(child->getPolicyLogit() + gumbel_noise[i]);   // 破壊的に加算
        }
    }
```

`addNoiseToNodeChildren` は `zero_actor.cpp:100` から，halving（L102）より**先に**呼ばれる．
したがって `actor_use_gumbel_noise = true` なら top-m の選抜にノイズが効く．

### 2-3. eval config の設定 [事実]

`xrl_viz/cfg/othello_8x8_gaz_eval_n{16,32,128}.cfg` の3本とも同一：

```
29:actor_use_dirichlet_noise=false # true for adding dirchlet noise to the policy
35:actor_use_gumbel_noise=false # true for adding Gumbel noise to the policy
```

実データでも裏が取れている：`post_n{16,32,128}.json` の全ノードで `p_noise` の値集合が `{0}`．

### 結論 [事実]

決定論 eval config では両ノイズが無効で `addNoiseToNodeChildren` は何もしない．
`policy_logit_` はネットワークの生 logit のままなので，
**top-m の選抜は「方策 logit の上位16手」という完全に確定的な選抜**である．

→ 候補から外れた手について「方策が有望でないと判断した手」という説明は**成立する**．
「たまたま外れた」ではない．

（この結論は eval config 限定．学習時の自己対戦は `actor_use_gumbel_noise` が真なので当てはまらない．）

---

## Step 3：凍結局面5（ply 58）の検証経路

### 判明したこと [事実]

1. **局面5 は n=128 の自己対戦記録の局面**であって，n16 の記録の局面ではない．
   - n16 記録の ply 58：手番 B，空マス **5**（局面5 の記述 空マス2 と不一致）
   - 旧 n128 記録の ply 58：手番 B，空マス **2**，k=2，実着手 **F8** → 局面5 の記述と一致
   - `replay.py` は n16 の局面列を流すものなので，そもそも局面5 は対象外だった．
     前回の「replay の範囲外」という報告は理由の説明として誤りで，正しくは**参照する対局が違う**．
2. **修正後の n=128 の対局は，着手が ply 13 から，盤面が ply 14 から分岐している．**
   ply 58 の盤面は修正前後で**一致しない**（`frozen_positions_check.csv`）．
   修正後の記録の ply 58 は k=2・空マス2 だが別の盤面で，実着手は F8 ではなく **A7**．
   → **局面5 は修正後の記録には同じ形では存在しない．**

### 補助数値の出所（**解決済み**．先の疑義は撤回する）[事実]

打ち直しで確認したところ，局面5 の補助数値は **F8 の子ノードの値**だった．
当方が root の値と突き合わせたのが誤りで，`frozen_positions.md` の記載は正しい．

| doc の記載 | 実測（n=128，打ち直し） |
|---|---|
| 実着手 F8 の読み回数 = 64 | F8 の `N = 64` ✓ |
| 第一印象 -0.373 | F8 の `v = -0.373` ✓ |
| 読んだあとの結論 +0.952 | F8 の `Q = +0.952` ✓ |

### 検証結果：局面5 は修正の影響を受けていない [事実]

旧 n128 の ply 0〜58 の着手列を打ち直した結果（`xrl_viz/data/ply58_check/`）：

| | n=16 | n=32 | n=128 |
|---|---|---|---|
| 修正前の着手 | F8 | F8 | F8 |
| 修正後の着手 | F8 | F8 | F8 |
| 修正後 F8 の N / Q / v | 8 / +0.613 / -0.373 | 16 / +0.807 / -0.373 | 64 / +0.952 / -0.373 |

- 到達した盤面は `frozen_positions.md` 局面5 の図と**完全一致**．
- 3水準すべてで，修正前後の着手・訪問数・Q・v が**完全に同一**．
- 「一目は不安（v = -0.373）だが読むと勝ち（Q = +0.952）」という局面の性質は保たれている．
- 生存2手は G8 と F8 で，n=128 では N が 64/64 の同数（Step 1 の観測と整合）．

**結論**：局面5 は差し替え不要．ただし記述は「旧 n=128 の着手列で到達する局面」であり，
修正後のエンジンの自己対戦はこの局面を通らない（対局が ply 13 から分岐するため）．
局面の同定は盤面図と着手列で行うべきで，「n=128 の対局の ply 58」という参照の仕方は
修正後は成り立たない．

### 使った経路（実行済み）

`xrl_viz/replay_line.py` を追加した．参照する棋譜と最大 ply を引数で取り，
着手列を `reg_genmove` + `play` で打ち直す．

- 着手列は旧 n128 記録の `played` からそのまま取れる [事実]．
  当該区間（ply 0〜58）に `Resign` は1件も無い（n128 の初出は ply 59）．
- 冗長な裏取りとして，連続する盤面の差分から実着手を復元する方法も確認済み．
  ply 0〜58 の **59/59 で復元に成功**し，記録の `played` と食い違いゼロ，全て合法手だった．
  `played` が `Resign` の区間を含む対局にも使える（`console.cpp:172` は着手を打ってから
  "Resign" と返すため，`played` だけでは着手が分からない）．


---

## 未処理・要判断

1. ~~Step 0-4 の修正案の選択~~ → **案B を適用済み**（root 直下のみ全出し）．
3. §2.3 の [要確認] を外すかの判断（docs は書き換えていない）．
4. 局面5 の補助数値の出所 [要確認]．
5. `xrl_viz/index.html` の実動確認 [要確認]．案B で root 直下に N=0 の子が増えたため，
   GUI の Gumbel スコア表（`index.html` の `drawArgmax`）が影響を受ける．
   実装は全 root 子に `p_logit + (50+Nmax)*q` を当てるが，エンジン側は
   `count == 0` の候補にスコアの下限値を入れる（gumbel_zero.cpp L148）．
   N=0 の手が本来より上位に並びうる．要修正の可能性あり．
