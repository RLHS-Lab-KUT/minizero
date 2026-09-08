#pragma once

#include "base_env.h"
#include "configuration.h"
#include <algorithm>
#include <array>
#include <bitset>
#include <string>
#include <unordered_map>
#include <vector>

namespace minizero::env::othello {
using namespace minizero::utils;
const std::string kOthelloName = "othello";
const int kOthelloNumPlayer = 2;
const int kMaxOthelloBoardSize = 16;
typedef std::bitset<kMaxOthelloBoardSize * kMaxOthelloBoardSize> OthelloBitboard;

typedef BaseBoardAction<kOthelloNumPlayer> OthelloAction;

// The four corners, in board-position order. Corners can never be flipped: getFlipPoint()
// only flips a run of opponent stones that is bracketed by one of our stones, and the two
// squares bracketing a corner along any line are off the board. So a corner changes state
// exactly once, empty -> colour.
const int kNumCornerAux = 4;
inline std::array<int, kNumCornerAux> getCornerPositions(int board_size)
{
    return {0,
            board_size - 1,
            board_size * (board_size - 1),
            board_size * board_size - 1};
}

class OthelloEnv : public BaseBoardEnv<OthelloAction> {
public:
    OthelloEnv()
    {
        assert(getBoardSize() <= kMaxOthelloBoardSize);
        reset();
    }

    void reset() override;
    bool act(const OthelloAction& action) override;
    bool act(const std::vector<std::string>& action_string_args) override;
    std::vector<OthelloAction> getLegalActions() const override;
    bool isLegalAction(const OthelloAction& action) const override;
    bool isTerminal() const override;
    float getReward() const override { return 0.0f; }
    float getEvalScore(bool is_resign = false) const override;
    std::vector<float> getFeatures(utils::Rotation rotation = utils::Rotation::kRotationNone) const override;
    std::vector<float> getActionFeatures(const OthelloAction& action, utils::Rotation rotation = utils::Rotation::kRotationNone) const override;
    // 4 base planes (+1 corner-threat plane when env_othello_use_corner_feature is set).
    inline int getNumInputChannels() const override { return config::env_othello_use_corner_feature ? 5 : 4; }
    inline int getPolicySize() const override { return getBoardSize() * getBoardSize() + 1; }
    std::string toString() const override;
    inline std::string name() const override { return kOthelloName + "_" + std::to_string(getBoardSize()) + "x" + std::to_string(getBoardSize()); }
    inline int getNumPlayer() const override { return kOthelloNumPlayer; }
    // XRL可視化用に追加(挙動非変更・読み取り専用): 指定マスの占有を返す(1=Player1, 2=Player2, 0=空)
    inline int getColorAtPosition(int position) const
    {
        if (board_.get(Player::kPlayer1)[position]) { return 1; }
        if (board_.get(Player::kPlayer2)[position]) { return 2; }
        return 0;
    }
    inline bool isPassAction(const OthelloAction& action) const { return (action.getActionID() == getBoardSize() * getBoardSize()); }

    inline int getRotatePosition(int position, utils::Rotation rotation) const override { return utils::getPositionByRotating(rotation, position, getBoardSize()); };
    inline int getRotateAction(int action_id, utils::Rotation rotation) const override { return getRotatePosition(action_id, rotation); };

    static void setUpEnv() { config::env_board_size = 8; }

private:
    Player eval() const;
    // These three only read their arguments, so they are const; getFeatures() needs to call
    // them from a const context to build the corner-threat plane.
    OthelloBitboard getCanPutPoint(
        int direction,
        OthelloBitboard mask,
        OthelloBitboard empty_board,
        OthelloBitboard opponent_board,
        OthelloBitboard player_board) const;
    OthelloBitboard getFlipPoint(
        int direction,
        OthelloBitboard mask,
        OthelloBitboard placed_pos,
        OthelloBitboard opponent_board,
        OthelloBitboard player_board) const;
    OthelloBitboard getCandidateAlongDirectionBoard(int direction, OthelloBitboard candidate) const;
    // Bit set on every legal move of the side to move that would make at least one corner a
    // legal move for the opponent. All-zero when the side to move can only pass.
    OthelloBitboard getCornerThreatBoard() const;
    std::string getCoordinateString() const;

    int dir_step_[8]; // 8 directions
    OthelloBitboard one_board_;
    OthelloBitboard mask_[8];               // 8 directions
    GamePair<bool> legal_pass_;             // store black/white legal pass
    GamePair<OthelloBitboard> legal_board_; // store black/white legal board
    GamePair<OthelloBitboard> board_;       // store black/white board
};

class OthelloEnvLoader : public BaseBoardEnvLoader<OthelloAction, OthelloEnv> {
public:
    std::vector<float> getActionFeatures(const int pos, utils::Rotation rotation = utils::Rotation::kRotationNone) const override;
    inline bool isPassAction(const OthelloAction& action) const { return (action.getActionID() == getBoardSize() * getBoardSize()); }
    inline std::vector<float> getValue(const int pos) const { return {getReturn()}; }
    inline std::string name() const override { return kOthelloName + "_" + std::to_string(getBoardSize()) + "x" + std::to_string(getBoardSize()); }
    inline int getPolicySize() const override { return getBoardSize() * getBoardSize() + 1; }
    inline int getRotatePosition(int position, utils::Rotation rotation) const override { return utils::getPositionByRotating(rotation, position, getBoardSize()); };
    inline int getRotateAction(int action_id, utils::Rotation rotation) const override { return getRotatePosition(action_id, rotation); };
};

} // namespace minizero::env::othello
