from __future__ import annotations

import math
import random
from typing import Optional

from .models import MCTSNode


class MCTSMixin:
    def _ucb_score(self, parent: MCTSNode, child: MCTSNode) -> float:
        if child.visits == 0:
            return float("inf")

        exploitation = child.total_reward / child.visits
        exploration = self.UCB_C * math.sqrt(
            math.log(parent.visits + 1.0) / child.visits
        )

        return exploitation + exploration

    def _progressive_widening_limit(self, node: MCTSNode) -> int:
        return max(1, int(self.PW_C * ((node.visits + 1) ** self.PW_ALPHA)))

    def _can_expand(self, node: MCTSNode) -> bool:
        return len(node.children) < self._progressive_widening_limit(node)

    def _expand(self, node: MCTSNode) -> Optional[MCTSNode]:
        actions = self._available_actions(node)

        for _ in range(60):
            action = random.choice(actions)
            child_obstacles = self._apply_action(node.obstacles, action)

            valid, _ = self._validate_test_case_rules(child_obstacles)
            if not valid:
                continue

            signature = self._scenario_signature(child_obstacles)

            if signature in self.seen_signatures:
                continue

            if signature in self.tree_signatures:
                continue

            child = MCTSNode(
                obstacles=child_obstacles,
                parent=node,
                action=action,
                node_id=self._next_node_id(),
            )

            node.children.append(child)
            self.tree_signatures.add(signature)
            return child

        return None

    def _tree_policy(self, root: MCTSNode) -> Optional[MCTSNode]:
        node = root

        for _ in range(20):
            if self._can_expand(node):
                expanded = self._expand(node)
                if expanded is not None:
                    return expanded

            if len(node.children) == 0:
                return self._expand(node)

            node = max(node.children, key=lambda child: self._ucb_score(node, child))

        return node

    def _backup(self, node: MCTSNode, reward: float) -> None:
        while node is not None:
            node.visits += 1
            node.total_reward += reward
            node.best_reward = max(node.best_reward, reward)
            node = node.parent
