# upstream issue 草案 — Gumbel の候補足切りが virtual loss 込みの値で行われる

提出先：rlglab/minizero
状態：**未提出**（本文は英語，このファイルの説明文は日本語）
対象コミット：`a07fd09`（fork 側．該当箇所は upstream と同一）
本文で引用する行番号はすべて修正前のもの．

---

## Title

`sequentialHalving` eliminates Gumbel candidates using virtual-loss-polluted values

## Body

### Summary

In console/GTP search (`ZeroActor::think`), the Gumbel sequential-halving
elimination runs *before* the virtual loss of the simulation that was just
backed up is removed. The elimination therefore scores candidates with
`getNormalizedMean()`, which folds `virtual_loss_` into the value. The candidate
that lies on the path just simulated is scored with a deflated value and can be
eliminated in place of a genuinely worse one.

This only affects search driven by `ZeroActor::step()`; self-play is unaffected
(see *Impact on self-play training* below).

### Where it happens

`afterNNEvaluation()` backs the simulation up and then immediately runs the
halving, while the virtual loss is still on the nodes:

```cpp
// minizero/actor/zero_actor.cpp
 88:            getMCTS()->backup(node_path, alphazero_output->value_, env_transition.getReward());
...
101:    if (isSearchDone()) { handleSearchDone(); }
102:    if (config::actor_use_gumbel) { gumbel_zero_.sequentialHalving(getMCTS()); }   // <-- elimination
103: }
```

`step()` only removes the virtual loss *after* `afterNNEvaluation()` returns:

```cpp
// minizero/actor/zero_actor.cpp  (ZeroActor::step, line 134)
150:        for (auto node : mcts_search_data_.node_path_) { node->addVirtualLoss(); }
...
158:        afterNNEvaluation(network_output[nn_evaluation_batch_id_]);            // <-- halving runs in here
159:        auto virtual_loss = mcts_search_data_.node_path_.back()->getVirtualLoss();
160:        for (auto node : mcts_search_data_.node_path_) { node->removeVirtualLoss(virtual_loss); }  // <-- too late
```

The call path from the halving down to the polluted value:

```
zero_actor.cpp:102   GumbelZero::sequentialHalving()
  gumbel_zero.cpp:110    if (next_budget > 0 && sample_size_ > 2)
  gumbel_zero.cpp:113        GumbelZero::sortCandidatesByScore()      // decides who is cut
  gumbel_zero.cpp:129/132        MCTSNode::getNormalizedMean()
  mcts.cpp:51                        value = (value * count_ - virtual_loss_) / getCountWithVirtualLoss();
```

`gumbel_zero.cpp:114` then drops everything past `sample_size_`, so the decision
is irreversible for the rest of the search.

The error is amplified before it reaches the ordering. At
`gumbel_zero.cpp:130/133` the value is scaled by
`(actor_gumbel_sigma_visit_c + max_child_count) * actor_gumbel_sigma_scale_c`,
which is at least 50 with the default `actor_gumbel_sigma_visit_c = 50`.

### When it triggers

Only when sequential halving actually runs. Halving is gated at
`gumbel_zero.cpp:109-110`:

```cpp
int next_budget = std::floor(config::actor_num_simulation / (std::log2(config::actor_gumbel_sample_size) * sample_size_ / 2));
if (next_budget > 0 && sample_size_ > 2) {
```

With the default `actor_gumbel_sample_size = 16` (`configuration.cpp:31`) this is
`floor(n / 32) > 0`, i.e. **`actor_num_simulation >= 32`**. At `n = 16` no halving
round ever runs and the bug is dormant, which makes `n = 16` a clean control.

### Reproduction

Othello 8x8, a deterministic evaluation config: `actor_use_gumbel = true`,
`actor_use_gumbel_noise = false`, `actor_use_dirichlet_noise = false`,
`actor_use_random_rotation_features = false`, `actor_select_action_by_count = true`,
`actor_mcts_think_batch_size = 1`, `actor_gumbel_sample_size = 16`.

To compare the same positions under two builds, replay one fixed move sequence
through the engine rather than letting it self-play (self-play diverges as soon
as one move changes):

```
clear_board
reg_genmove b        # search without playing
tree_json            # dump the search tree
play b <move>        # advance along the fixed line
reg_genmove w
tree_json
play w <move>
...
```

Run this against the same 48-position line at `n = 16`, `32`, `128`, once with
an unmodified build and once with the fix below, and diff the root children.

### Measured effect

48 positions, identical in both runs. "rounds" counts halving rounds
(48 positions x 3 rounds = 144 at `n >= 32`; `n = 16` runs zero rounds).

| n | moves changed | positions with a different root visit distribution | rounds whose elimination set changed |
|---|---|---|---|
| 16 | 0 | 0 / 48 | 0 / 0 (halving never runs) |
| 32 | 1 | 6 / 48 | 9 / 144 |
| 128 | 3 | 9 / 48 | 13 / 144 |

The number of candidates cut in each round is identical before and after the fix
(`round 0: 147, round 1: 157, round 2: 95` at both `n = 32` and `n = 128`), so the
halving schedule itself is unchanged — only *which* candidates get cut changes.

Example at `n = 128`: the move chosen at three of the 48 positions changes
(`E7 -> B4`, `B6 -> A3`, `H5 -> A7`).

### Impact on self-play training

None. `addVirtualLoss()` / `removeVirtualLoss()` are called only from
`ZeroActor::step()` (`zero_actor.cpp:150` and `:160`), and `step()` is reached only
from `ZeroActor::think()` (`zero_actor.cpp:41`). Self-play drives the actors through
`ActorGroup`, which calls `beforeNNEvaluation()` / `afterNNEvaluation()` directly
(`actor_group.cpp:91` and `:94`) and never touches the virtual loss. During
self-play `virtual_loss_` stays 0, so `getNormalizedMean()` already returns the
unpolluted value.

### Suggested fix

Virtual loss exists to spread concurrent selections apart. It should not
influence *which* action survives a halving round. The narrowest fix is to score
the elimination with a virtual-loss-free value, leaving the timing untouched:

```cpp
// mcts.cpp — same as getNormalizedMean() without the virtual-loss line
float MCTSNode::getNormalizedMeanWithoutVirtualLoss(const std::map<float, int>& tree_value_bound) const
{
    float value = reward_ + config::actor_mcts_reward_discount * mean_;
    if (config::actor_mcts_value_rescale) {
        if (tree_value_bound.size() < 2) { return 1.0f; }
        const float value_lower_bound = tree_value_bound.begin()->first;
        const float value_upper_bound = tree_value_bound.rbegin()->first;
        value = (value - value_lower_bound) / (value_upper_bound - value_lower_bound);
        value = fmin(1, fmax(-1, 2 * value - 1));
    }
    value = (action_.getPlayer() == env::charToPlayer(config::actor_mcts_value_flipping_player) ? -value : value);
    return value;
}
```

and use it at `gumbel_zero.cpp:129` and `:132` inside `sortCandidatesByScore()`.

This also covers the final action choice, since `decideActionNode()` goes through
the same `sortCandidatesByScore()` (`gumbel_zero.cpp:60-65`).

An alternative is to move the virtual-loss removal in `step()` ahead of the
`afterNNEvaluation()` call. That is a smaller edit, but it leaves the virtual
losses of the *other* in-flight queries on the tree when
`actor_mcts_think_batch_size > 1`, so it does not fully remove the pollution.
Note also that the halving call cannot simply be lifted out of
`afterNNEvaluation()` into `step()`: self-play would then never run sequential
halving at all.

---

## 提出前に確認すること

- 再現手順は othello 8x8 の自作モデルに依存しない形に書き直すか，
  upstream の公開モデルで再現を取り直すか決める．
- 表の数値は fork 側の計装（`gaz_eliminated_round`）を前提にしている．
  upstream には無いフィールドなので，本文では「淘汰集合の差」という
  観測量の定義を先に書く必要がある．
- `actor_mcts_think_batch_size > 1` での実測は取っていない（eval は 1 固定）．
  本文でもバッチ>1 は「推論」として書いており，実測値は主張していない．
