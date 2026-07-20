#include "gumbel_zero.h"
#include <algorithm>
#include <limits>
#include <memory>
#include <unordered_map>

namespace minizero::actor {

std::string GumbelZero::getMCTSPolicy(const std::shared_ptr<MCTS>& mcts) const
{
    // calculate value for non-visisted nodes
    float pi_sum = 0.0f, q_sum = 0.0f;
    for (int i = 0; i < mcts->getRootNode()->getNumChildren(); ++i) {
        MCTSNode* child = mcts->getRootNode()->getChild(i);
        if (child->getCount() == 0) { continue; }
        float value = child->getNormalizedMean(mcts->getTreeValueBound());
        pi_sum += child->getPolicy();
        q_sum += child->getPolicy() * value;
    }
    float value_pi = mcts->getRootNode()->getValue();
    if (config::actor_mcts_value_rescale) {
        if (mcts->getTreeValueBound().size() < 2) {
            value_pi = 1.0f;
        } else {
            const float value_lower_bound = mcts->getTreeValueBound().begin()->first;
            const float value_upper_bound = mcts->getTreeValueBound().rbegin()->first;
            value_pi = (value_pi - value_lower_bound) / (value_upper_bound - value_lower_bound);
            value_pi = fmin(1, fmax(-1, 2 * value_pi - 1));
        }
    }
    value_pi = (mcts->getRootNode()->getChild(0)->getAction().getPlayer() == env::charToPlayer(config::actor_mcts_value_flipping_player) ? -value_pi : value_pi);
    float non_visited_node_value = 1.0 / (1 + config::actor_num_simulation) * (value_pi + (config::actor_num_simulation / pi_sum) * q_sum);

    // calculate completed Q-values
    std::unordered_map<int, float> new_logits;
    float max_logit = -std::numeric_limits<float>::max();
    float max_child_count = 0;
    for (int i = 0; i < mcts->getRootNode()->getNumChildren(); ++i) { max_child_count = fmax(max_child_count, mcts->getRootNode()->getChild(i)->getCount()); }
    for (int i = 0; i < mcts->getRootNode()->getNumChildren(); ++i) {
        MCTSNode* child = mcts->getRootNode()->getChild(i);
        float value = (child->getCount() == 0 ? non_visited_node_value : child->getNormalizedMean(mcts->getTreeValueBound()));
        float logit_without_noise = child->getPolicyLogit() - child->getPolicyNoise();
        float score = logit_without_noise + (config::actor_gumbel_sigma_visit_c + max_child_count) * config::actor_gumbel_sigma_scale_c * value;
        new_logits.insert({child->getAction().getActionID(), score});
        max_logit = fmax(max_logit, score);
    }

    // return normalized completed Q-values
    std::ostringstream oss;
    for (auto& logit : new_logits) {
        logit.second = logit.second - max_logit;
        if (logit.second < -38)
            continue;
        oss << (oss.str().empty() ? "" : ",")
            << logit.first << ":" << exp(logit.second);
    }
    return oss.str();
}

MCTSNode* GumbelZero::decideActionNode(const std::shared_ptr<MCTS>& mcts)
{
    if (config::actor_select_action_by_count) {
        assert(candidates_.size() > 0);
        sortCandidatesByScore(mcts);
        return candidates_[0];
    } else if (config::actor_select_action_by_softmax_count) {
        return mcts->selectChildBySoftmaxCount(mcts->getRootNode(), config::actor_select_action_softmax_temperature);
    }

    assert(false);
    return nullptr;
}

std::vector<MCTSNode*> GumbelZero::selection(const std::shared_ptr<MCTS>& mcts)
{
    std::vector<MCTSNode*> node_path;
    if (mcts->getNumSimulation() == 0) {
        node_path = mcts->select();
    } else {
        assert(candidates_.size() > 0);
        sort(candidates_.begin(), candidates_.end(), [](const MCTSNode* lhs, const MCTSNode* rhs) {
            return (lhs->getCount() < rhs->getCount() || (lhs->getCount() == rhs->getCount() && lhs->getPolicyLogit() > rhs->getPolicyLogit()));
        });
        node_path = mcts->selectFromNode(candidates_[0]);
        node_path.insert(node_path.begin(), mcts->getRootNode());
    }
    return node_path;
}

void GumbelZero::sequentialHalving(const std::shared_ptr<MCTS>& mcts)
{
    if (mcts->getNumSimulation() == 1) {
        // collect candidates
        candidates_.clear();
        for (int i = 0; i < mcts->getRootNode()->getNumChildren(); ++i) { candidates_.push_back(mcts->getRootNode()->getChild(i)); }
        sort(candidates_.begin(), candidates_.end(), [](const MCTSNode* lhs, const MCTSNode* rhs) { return lhs->getPolicyLogit() > rhs->getPolicyLogit(); });
        // trace: every root child starts as a surviving candidate (-1); the ones the top-m
        // sampling drops below are marked -2. Runs once per search (getNumSimulation() == 1
        // holds only right after the root's initial inference), so halving_round_ is reset here.
        for (auto node : candidates_) { node->setGumbelEliminatedRound(-1); }
        if (static_cast<int>(candidates_.size()) > config::actor_gumbel_sample_size) {
            for (int i = config::actor_gumbel_sample_size; i < static_cast<int>(candidates_.size()); ++i) { candidates_[i]->setGumbelEliminatedRound(-2); }
            candidates_.resize(config::actor_gumbel_sample_size);
        }
        sample_size_ = config::actor_gumbel_sample_size;
        halving_round_ = 0;
        simulation_budget_ = std::max(1.0, std::floor(config::actor_num_simulation / (std::log2(config::actor_gumbel_sample_size) * sample_size_)));
    } else {
        bool all_candidates_reach_budget = true;
        for (auto node : candidates_) {
            if (node->getCount() >= simulation_budget_) { continue; }
            all_candidates_reach_budget = false;
            break;
        }

        if (all_candidates_reach_budget) {
            int next_budget = std::floor(config::actor_num_simulation / (std::log2(config::actor_gumbel_sample_size) * sample_size_ / 2));
            if (next_budget > 0 && sample_size_ > 2) {
                sample_size_ /= 2;
                assert(sample_size_ > 0);
                sortCandidatesByScore(mcts);
                if (static_cast<int>(candidates_.size()) > sample_size_) {
                    // trace: record which candidates this halving round cut
                    for (int i = sample_size_; i < static_cast<int>(candidates_.size()); ++i) { candidates_[i]->setGumbelEliminatedRound(halving_round_); }
                    candidates_.resize(sample_size_);
                }
                ++halving_round_;
                simulation_budget_ = candidates_[0]->getCount() + next_budget;
            }
        }
    }
}

void GumbelZero::sortCandidatesByScore(const std::shared_ptr<MCTS>& mcts)
{
    assert(!candidates_.empty());
    float max_child_count = 0;
    for (int i = 0; i < mcts->getRootNode()->getNumChildren(); ++i) { max_child_count = fmax(max_child_count, mcts->getRootNode()->getChild(i)->getCount()); }
    auto& tree_value_bound = mcts->getTreeValueBound();
    // Score each candidate once and cache it on the node, then sort by the cached score.
    // getNormalizedMean() is a side-effect-free const member, so scoring once per node instead
    // of once per comparison yields the same values and the same ordering; caching only makes
    // the score observable for the search trace (gaz_decision_score).
    const float min_value = -std::numeric_limits<float>::max();
    for (auto node : candidates_) {
        float value = node->getNormalizedMean(tree_value_bound);
        float score = node->getPolicyLogit() + (config::actor_gumbel_sigma_visit_c + max_child_count) * config::actor_gumbel_sigma_scale_c * value;
        node->setGumbelDecisionScore(node->getCount() > 0 ? score : min_value);
    }
    sort(candidates_.begin(), candidates_.end(), [](const MCTSNode* lhs, const MCTSNode* rhs) {
        return lhs->getGumbelDecisionScore() > rhs->getGumbelDecisionScore();
    });
}

} // namespace minizero::actor
