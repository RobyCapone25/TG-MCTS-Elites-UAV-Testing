from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from aerialist.px4.obstacle import Obstacle

from .models import EvalResult, MCTSNode


class PlottingMixin:
    def _status_style(self, min_distance: float) -> Tuple[str, str]:
        if min_distance < self.CRITICAL_PROXIMITY_THRESHOLD:
            return "red", "CRITICAL PROXIMITY (5-point band)"
        if min_distance < self.FAILURE_THRESHOLD:
            return "red", "OFFICIAL FAILURE"
        if min_distance < self.NEAR_MISS_THRESHOLD:
            return "orange", "NEAR MISS"
        return "green", "SAFE"

    def _save_scenario_plot(
        self,
        test: Any,
        obstacles: List[Obstacle],
        index: int,
        min_distance: float,
        point: int,
        node_id: int,
        mission_status: str,
        output_dir: Optional[str] = None,
    ) -> str:
        points, actual_xy = self._extract_trajectory_xy(test)
        times, xs, ys, zs, actual_series = self._extract_trajectory_series(test)
        actual = actual_xy or actual_series

        target_dir = output_dir or self.scenario_plot_dir
        os.makedirs(target_dir, exist_ok=True)
        filename = "trajectory_overview.png" if output_dir is not None else f"trajectory_overview_attempt_{index:03d}_node_{node_id:03d}.png"
        path = os.path.abspath(os.path.join(target_dir, filename))

        fig = plt.figure(figsize=(12, 8))
        grid = GridSpec(3, 2, figure=fig, width_ratios=[1.0, 1.0], wspace=0.07, hspace=0.38)
        ax_x = fig.add_subplot(grid[0, 0])
        ax_y = fig.add_subplot(grid[1, 0], sharex=ax_x)
        ax_z = fig.add_subplot(grid[2, 0], sharex=ax_x)
        ax_xy = fig.add_subplot(grid[:, 1])

        line_kwargs = dict(linewidth=2.0)
        x_line, = ax_x.plot(times, xs, label="tests", **line_kwargs)
        ax_y.plot(times, ys, **line_kwargs)
        ax_z.plot(times, zs, **line_kwargs)

        if obstacles:
            obstacle_proxy = Rectangle((0, 0), 1, 1, facecolor="tab:gray", edgecolor="black", alpha=0.45)
            fig.legend([obstacle_proxy, x_line], ["obstacle", "tests"], loc="upper center", ncol=2, frameon=True, bbox_to_anchor=(0.5, 0.985))
        else:
            fig.legend([x_line], ["tests"], loc="upper center", ncol=1, frameon=True, bbox_to_anchor=(0.5, 0.985))

        ax_x.set_ylabel("X (m)")
        ax_y.set_ylabel("Y (m)")
        ax_z.set_ylabel("Z (m)")
        ax_z.set_xlabel("flight time (s)")

        for ax in (ax_x, ax_y, ax_z):
            ax.grid(False)
        min_t = min(times) if times else 0.0
        max_t = max(times) if times else 1.0
        if abs(max_t - min_t) < 1e-9:
            max_t = min_t + 1.0
        ax_z.set_xlim(min_t, max_t)

        for obs in obstacles:
            corners = self._rotated_corners(obs)
            poly = Polygon(corners, closed=True, alpha=0.45, edgecolor="black", facecolor="tab:gray")
            ax_xy.add_patch(poly)
        if actual:
            ax_xy.plot(xs, ys, linewidth=2.0)
        else:
            ax_xy.plot(xs, ys, linewidth=2.0, linestyle=":")

        ax_xy.set_xlabel("X (m)")
        ax_xy.set_ylabel("Y (m)")
        ax_xy.yaxis.set_label_position("right")
        ax_xy.yaxis.tick_right()
        ax_xy.grid(False)
        ax_xy.axis("equal")

        x_candidates = [self.X_MIN, self.X_MAX] + xs
        y_candidates = [0.0, self.Y_MIN, self.Y_MAX] + ys
        for obs in obstacles:
            for cx, cy in self._rotated_corners(obs):
                x_candidates.append(cx)
                y_candidates.append(cy)
        ax_xy.set_xlim(min(x_candidates) - 2.5, max(x_candidates) + 2.5)
        ax_xy.set_ylim(min(y_candidates) - 2.5, max(y_candidates) + 2.5)

        title_color, status = self._status_style(min_distance)
        algorithm_name = getattr(self, "ALGORITHM_NAME", "TG-MCTS-Elites")
        fig.suptitle(
            f"{algorithm_name} attempt {index} | node {node_id} | {status}\n"
            f"min_distance = {min_distance:.3f} m | point = {point} | trajectory = {actual} | "
            f"mission = {mission_status} | evidence = {getattr(test, 'failure_evidence', 'none')}",
            color=title_color,
            y=0.93,
        )
        plt.tight_layout(rect=(0.02, 0.03, 0.98, 0.90))
        plt.savefig(path, dpi=180)
        plt.close(fig)
        test.plot_file = path
        return path

    def _save_xy_time_plot(
        self,
        test: Any,
        obstacles: List[Obstacle],
        index: int,
        node_id: int,
        output_dir: Optional[str] = None,
    ) -> str:
        times, xs, ys, _zs, _actual = self._extract_trajectory_series(test)
        target_dir = output_dir or self.scenario_plot_dir
        os.makedirs(target_dir, exist_ok=True)
        filename = "trajectory_xy_time.png" if output_dir is not None else f"trajectory_xy_time_attempt_{index:03d}_node_{node_id:03d}.png"
        path = os.path.abspath(os.path.join(target_dir, filename))

        fig = plt.figure(figsize=(9, 6.5))
        ax = fig.add_subplot(111, projection="3d")
        ax.plot(xs, ys, times, linewidth=2.0)
        if xs and ys and times:
            ax.scatter([xs[0]], [ys[0]], [times[0]], s=45)
            ax.scatter([xs[-1]], [ys[-1]], [times[-1]], s=55, marker="^")

        base_t = min(times) if times else 0.0
        for obs in obstacles:
            corners = self._rotated_corners(obs)
            cycle = corners + [corners[0]]
            cx = [point[0] for point in cycle]
            cy = [point[1] for point in cycle]
            cz = [base_t for _ in cycle]
            ax.plot(cx, cy, cz, linewidth=1.2, alpha=0.7)

        ax.set_xlabel("X (m)")
        ax.set_ylabel("Y (m)")
        ax.set_zlabel("flight time (s)")
        ax.set_title(f"Trajectory in (X, Y, t) — attempt {index}, node {node_id}")
        plt.tight_layout()
        plt.savefig(path, dpi=180)
        plt.close(fig)
        test.xy_time_plot_file = path
        return path

    def _record_history(self, simulation_index: int, node: MCTSNode, result: EvalResult) -> None:
        parent_id = node.parent.node_id if node.parent is not None else None
        obstacle_text = []
        for obs in result.obstacles:
            obstacle_text.append(
                f"x={float(obs.position.x):.3f},y={float(obs.position.y):.3f},"
                f"l={float(obs.size.l):.3f},w={float(obs.size.w):.3f},"
                f"h={float(obs.size.h):.3f},r={float(obs.position.r):.3f}"
            )
        row = {
            "simulation_attempt": simulation_index,
            "node_id": node.node_id,
            "parent_id": parent_id,
            "action": node.action,
            "n_obstacles": len(result.obstacles),
            "min_distance": result.min_distance,
            "problem_type": self._problem_label(result.min_distance),
            "mission_status": result.mission_status,
            "failure_evidence": result.failure_evidence,
            "compliance_status": result.compliance_status,
            "point": result.point,
            "reward": result.reward,
            "cell": str(result.cell),
            "artifacts_saved": result.artifacts_saved,
            "scenario_plot": result.scenario_plot,
            "xy_time_plot": result.xy_time_plot,
            "yaml_file": result.yaml_file,
            "log_file": result.log_file,
            "obstacles": " | ".join(obstacle_text),
        }
        self.history.append(row)
        self._append_jsonl(self.history_jsonl_path, row)

    def _save_history_csv(self) -> None:
        path = os.path.join(self.output_dir, "history.csv")
        if len(self.history) == 0:
            return
        fieldnames = list(self.history[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.history)
        print(f"History saved to: {path}")

    def _collect_nodes(self, root: MCTSNode) -> List[MCTSNode]:
        nodes = []
        def dfs(node: MCTSNode):
            nodes.append(node)
            for child in node.children:
                dfs(child)
        dfs(root)
        return nodes

    def _node_depth(self, node: MCTSNode) -> int:
        depth = 0
        while node.parent is not None:
            depth += 1
            node = node.parent
        return depth

    def _tree_marker_and_color(self, node: MCTSNode) -> Tuple[str, str, str]:
        if node.eval_result is None:
            return "o", "lightgray", "Unevaluated/internal"
        distance = node.eval_result.min_distance
        if distance < self.CRITICAL_PROXIMITY_THRESHOLD:
            return "x", "red", f"Critical proximity: d < {self.CRITICAL_PROXIMITY_THRESHOLD:g} m"
        if distance < self.FAILURE_THRESHOLD:
            return "x", "red", f"Official proximity failure: d < {self.FAILURE_THRESHOLD:g} m"
        if distance < self.NEAR_MISS_THRESHOLD:
            return "^", "orange", f"Near miss: {self.FAILURE_THRESHOLD:g} m <= d < {self.NEAR_MISS_THRESHOLD:g} m"
        return "o", "green", f"Safe: d >= {self.NEAR_MISS_THRESHOLD:g} m"

    def _save_tree_plot(self, root: MCTSNode) -> None:
        nodes = self._collect_nodes(root)
        if len(nodes) == 0:
            return
        levels = {}
        for node in nodes:
            depth = self._node_depth(node)
            levels.setdefault(depth, []).append(node)
        for depth in levels:
            levels[depth].sort(key=lambda n: n.node_id)

        positions = {}
        x_spacing = 1.0
        max_level_width = max(len(level_nodes) for level_nodes in levels.values())
        for depth, level_nodes in levels.items():
            count = len(level_nodes)
            start_x = -0.5 * x_spacing * (count - 1)
            for idx, node in enumerate(level_nodes):
                positions[node.node_id] = (start_x + idx * x_spacing, -float(depth))

        fig_width = max(14.0, max_level_width * 0.75 + 3.0)
        fig_height = max(6.5, len(levels) * 1.4 + 1.5)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))

        for node in nodes:
            if node.parent is None:
                continue
            x, y = positions[node.node_id]
            px, py = positions[node.parent.node_id]
            ax.plot([px, x], [py, y], color="0.75", linewidth=0.6, zorder=1)

        label_boxes = []
        for node in nodes:
            x, y = positions[node.node_id]
            marker, color, _label = self._tree_marker_and_color(node)
            size = 52 if marker != "x" else 72
            ax.scatter([x], [y], s=size, marker=marker, color=color, edgecolor="black" if marker != "x" else None, linewidths=0.8, zorder=3)

            if node.eval_result is not None:
                distance = node.eval_result.min_distance
                reward = node.eval_result.reward
                label = f"{node.node_id}\n{distance:.1f}m\n{reward:.1f}"
            else:
                label = f"{node.node_id}"
            text = ax.annotate(
                label,
                (x, y),
                xytext=(0, 9),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=5.5,
                zorder=4,
            )
            label_boxes.append(text)

        legend_elements = [
            Line2D([0], [0], marker='x', color='red', linestyle='None', markersize=8, label=f'Critical proximity: d < {self.CRITICAL_PROXIMITY_THRESHOLD:g} m'),
            Line2D([0], [0], marker='x', color='red', linestyle='None', markersize=8, label=f'Official proximity failure: d < {self.FAILURE_THRESHOLD:g} m'),
            Line2D([0], [0], marker='^', color='orange', linestyle='None', markersize=6, label=f'Near miss: {self.FAILURE_THRESHOLD:g} m <= d < {self.NEAR_MISS_THRESHOLD:g} m'),
            Line2D([0], [0], marker='o', color='green', linestyle='None', markersize=6, label=f'Safe: d >= {self.NEAR_MISS_THRESHOLD:g} m'),
            Line2D([0], [0], marker='o', color='lightgray', linestyle='None', markersize=6, label='Unevaluated/internal'),
        ]
        ax.legend(handles=legend_elements, loc='upper right', frameon=True, fontsize=8)
        ax.set_title(f'{getattr(self, "ALGORITHM_NAME", "TG-MCTS-Elites")} generated search structure')
        ax.set_xlabel('Tree branching')
        ax.set_ylabel('Tree depth')
        ax.grid(True, alpha=0.2)
        ax.set_ylim(min(y for _x, y in positions.values()) - 0.2, 0.2)
        xs = [x for x, _y in positions.values()]
        pad = 1.0
        ax.set_xlim(min(xs) - pad, max(xs) + pad)

        path_primary = os.path.join(self.output_dir, "mcts_tree.png")
        path_alias = os.path.join(self.output_dir, "tree_final.png")
        plt.tight_layout()
        plt.savefig(path_primary, dpi=180)
        plt.savefig(path_alias, dpi=180)
        plt.close(fig)
        print(f"Tree plot saved to: {path_primary}")

    def _history_records(self) -> List[Tuple[int, float, float, int]]:
        records = []
        for fallback_index, row in enumerate(self.history, start=1):
            try:
                attempt = int(row.get("simulation_attempt", fallback_index))
                min_distance = float(row["min_distance"])
                reward = float(row["reward"])
                point = int(row.get("point", 0))
            except (KeyError, TypeError, ValueError):
                continue
            records.append((attempt, min_distance, reward, point))
        records.sort(key=lambda item: item[0])
        return records

    def _save_min_distance_progress_plot(self, records: List[Tuple[int, float, float, int]]) -> None:
        attempts = [item[0] for item in records]
        distances = [item[1] for item in records]
        best_distances = []
        best = float("inf")
        for value in distances:
            best = min(best, value)
            best_distances.append(best)
        fig, ax = plt.subplots(figsize=(10.5, 4.8))
        ax.plot(attempts, distances, marker="o", markersize=3.5, linewidth=1.0, alpha=0.6, label="Minimum distance per evaluation")
        ax.plot(attempts, best_distances, linewidth=2.3, label="Best minimum distance so far")
        for threshold, label in [
            (self.CRITICAL_PROXIMITY_THRESHOLD, f"5-point boundary ({self.CRITICAL_PROXIMITY_THRESHOLD:g} m)"),
            (1.0, "2-to-1-point boundary (1 m)"),
            (self.FAILURE_THRESHOLD, f"Official failure boundary ({self.FAILURE_THRESHOLD:g} m)"),
            (self.NEAR_MISS_THRESHOLD, f"Near-miss boundary ({self.NEAR_MISS_THRESHOLD:g} m)"),
        ]:
            ax.axhline(threshold, linestyle="--", linewidth=1.0, alpha=0.7, label=label)
        ax.set_xlabel("Simulator attempt")
        ax.set_ylabel("Minimum distance (m)")
        ax.set_title("Minimum-distance trend")
        ax.set_ylim(bottom=0.0)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8, ncol=2)
        plt.tight_layout()
        path = os.path.join(self.output_dir, "progress_min_distance.png")
        plt.savefig(path, dpi=180)
        plt.close(fig)
        print(f"Progress plot saved to: {path}")

    def _save_reward_progress_plot(self, records: List[Tuple[int, float, float, int]]) -> None:
        attempts = [item[0] for item in records]
        rewards = [item[2] for item in records]
        best_rewards = []
        best = -float("inf")
        for value in rewards:
            best = max(best, value)
            best_rewards.append(best)
        fig, ax = plt.subplots(figsize=(10.5, 4.8))
        ax.plot(attempts, rewards, marker="o", markersize=3.5, linewidth=1.0, alpha=0.6, label="Reward per evaluation")
        ax.plot(attempts, best_rewards, linewidth=2.3, label="Best reward so far")
        ax.set_xlabel("Simulator attempt")
        ax.set_ylabel("Reward")
        ax.set_title("Reward trend")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8)
        plt.tight_layout()
        path = os.path.join(self.output_dir, "progress_reward.png")
        plt.savefig(path, dpi=180)
        plt.close(fig)
        print(f"Progress plot saved to: {path}")

    def _save_reward_vs_distance_plot(self, records: List[Tuple[int, float, float, int]]) -> None:
        distances = [item[1] for item in records]
        rewards = [item[2] for item in records]
        attempts = [item[0] for item in records]
        points = [item[3] for item in records]
        fig, ax = plt.subplots(figsize=(8.5, 6.0))
        scatter = ax.scatter(distances, rewards, s=26)
        for attempt, distance, reward, point in records:
            ax.annotate(f"{attempt}", (distance, reward), xytext=(4, 4), textcoords="offset points", fontsize=6)
        ax.set_xlabel("Minimum distance (m)")
        ax.set_ylabel("Reward")
        ax.set_title("Reward versus minimum distance")
        ax.grid(True, alpha=0.25)
        for threshold in (self.CRITICAL_PROXIMITY_THRESHOLD, 1.0, self.FAILURE_THRESHOLD, self.NEAR_MISS_THRESHOLD):
            ax.axvline(threshold, linestyle="--", linewidth=0.9, alpha=0.35)
        plt.tight_layout()
        path = os.path.join(self.output_dir, "progress_reward_vs_distance.png")
        plt.savefig(path, dpi=180)
        plt.close(fig)
        print(f"Progress plot saved to: {path}")

    def _save_progress_plots(self) -> None:
        if len(self.history) == 0:
            return
        records = self._history_records()
        if not records:
            return
        self._save_min_distance_progress_plot(records)
        self._save_reward_progress_plot(records)
        self._save_reward_vs_distance_plot(records)

    def _save_all_outputs(self, root: MCTSNode) -> None:
        self._save_history_csv()
        self._save_progress_plots()
        self._save_tree_plot(root)

    def _export_best_ranked_summary(self, test_cases: List[Any]) -> None:
        os.makedirs(self.best_ranked_dir, exist_ok=True)
        rows = []
        for idx, test_case in enumerate(test_cases, start=1):
            folder_name = (
                f"rank_{idx:02d}_point_{getattr(test_case, 'official_point', 'x')}_"
                f"distance_{str(round(float(getattr(test_case, 'minimum_distance', 0.0)), 3)).replace('.', 'p')}_"
                f"attempt_{getattr(test_case, 'simulation_attempt', 'na')}"
            )
            case_dir = Path(self.best_ranked_dir) / folder_name
            case_dir.mkdir(parents=True, exist_ok=True)
            yaml_path = case_dir / "test.yaml"
            log_path = case_dir / "flight.ulg"
            overview_path = case_dir / "trajectory_overview.png"
            xy_time_path = case_dir / "trajectory_xy_time.png"
            if getattr(test_case, 'yaml_file', ''):
                test_case.save_yaml(str(yaml_path))
            if getattr(test_case, 'log_file', '') and os.path.exists(test_case.log_file):
                import shutil
                shutil.copy2(test_case.log_file, log_path)
            if getattr(test_case, 'plot_file', '') and os.path.exists(test_case.plot_file):
                import shutil
                shutil.copy2(test_case.plot_file, overview_path)
            if getattr(test_case, 'xy_time_plot_file', '') and os.path.exists(test_case.xy_time_plot_file):
                import shutil
                shutil.copy2(test_case.xy_time_plot_file, xy_time_path)
            metadata = {
                "rank": idx,
                "minimum_distance": getattr(test_case, 'minimum_distance', None),
                "official_point": getattr(test_case, 'official_point', None),
                "reward": getattr(test_case, 'reward', None),
                "problem_type": getattr(test_case, 'problem_type', None),
                "mission_status": getattr(test_case, 'mission_status', None),
                "failure_evidence": getattr(test_case, 'failure_evidence', None),
            }
            with open(case_dir / "metadata.json", "w", encoding="utf-8") as stream:
                json.dump(metadata, stream, indent=2)
            rows.append({
                "rank": idx,
                "folder": folder_name,
                "minimum_distance": getattr(test_case, 'minimum_distance', ''),
                "official_point": getattr(test_case, 'official_point', ''),
                "reward": getattr(test_case, 'reward', ''),
                "problem_type": getattr(test_case, 'problem_type', ''),
                "mission_status": getattr(test_case, 'mission_status', ''),
                "failure_evidence": getattr(test_case, 'failure_evidence', ''),
            })
        with open(Path(self.best_ranked_dir) / "ranking.csv", "w", newline="", encoding="utf-8") as stream:
            fieldnames = ["rank", "folder", "minimum_distance", "official_point", "reward", "problem_type", "mission_status", "failure_evidence"]
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
