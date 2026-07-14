#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


RANDOM_ID = "operator_random_search"
TG_ID = "tg_mcts_elites"
ALGORITHM_ORDER = (RANDOM_ID, TG_ID)
ALGORITHM_LABELS = {
    RANDOM_ID: "Operator-Matched\nRandom Search",
    TG_ID: "TG-MCTS-Elites",
}


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    axis_label: str
    higher_is_better: bool
    percentage: bool = False
    integer: bool = False
    censored_at_budget: bool = False


PRIMARY_METRICS: Tuple[MetricSpec, ...] = (
    MetricSpec(
        key="failure_yield_returnable",
        label="Returnable failure yield",
        axis_label="Returnable failures / simulator attempt",
        higher_is_better=True,
        percentage=True,
    ),
    MetricSpec(
        key="diverse_failures_returned",
        label="Diverse failures returned",
        axis_label="Number of final diverse failures",
        higher_is_better=True,
        integer=True,
    ),
    MetricSpec(
        key="best_min_distance",
        label="Best minimum distance",
        axis_label="Minimum UAV–obstacle distance (m)",
        higher_is_better=False,
    ),
    MetricSpec(
        key="time_to_first_official_failure_attempt",
        label="Attempt to first official failure",
        axis_label="Simulator attempt",
        higher_is_better=False,
        integer=True,
        censored_at_budget=True,
    ),
    MetricSpec(
        key="archive_coverage",
        label="Archive coverage",
        axis_label="Fraction of nominal archive cells",
        higher_is_better=True,
        percentage=True,
    ),
    MetricSpec(
        key="mean_failure_reproducibility_returnable",
        label="Failure reproducibility",
        axis_label="Reproduced official-failure fraction",
        higher_is_better=True,
        percentage=True,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate paired benchmark plots from raw_runs.csv. The plots show "
            "every seed explicitly and are suitable for very small samples such as n=2."
        )
    )
    parser.add_argument(
        "--raw-runs",
        type=Path,
        default=Path("results/benchmark_comparison/raw_runs.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/benchmark_comparison/plots"),
    )
    return parser.parse_args()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_")
    return text.lower() or "unknown"


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_raw_runs(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Benchmark raw-run file not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _newer(left: Mapping[str, str], right: Mapping[str, str]) -> Mapping[str, str]:
    """Return the latest duplicate run using generated_at, then summary path."""
    left_key = (str(left.get("generated_at", "")), str(left.get("summary_file", "")))
    right_key = (str(right.get("generated_at", "")), str(right.get("summary_file", "")))
    return right if right_key >= left_key else left


def deduplicate_runs(rows: Iterable[Mapping[str, str]]) -> List[Dict[str, str]]:
    latest: MutableMapping[Tuple[str, str, int, int], Mapping[str, str]] = {}
    for row in rows:
        mission = str(row.get("mission_label", "unknown"))
        algorithm = str(row.get("algorithm_id", "unknown"))
        seed = _as_int(row.get("seed"))
        budget = _as_int(row.get("budget"))
        if seed is None or budget is None:
            continue
        key = (mission, algorithm, seed, budget)
        latest[key] = _newer(latest[key], row) if key in latest else row
    return [dict(row) for _, row in sorted(latest.items())]


def _paired_groups(
    rows: Sequence[Mapping[str, str]],
) -> Dict[Tuple[int, str], Dict[int, Dict[str, Mapping[str, str]]]]:
    groups: Dict[Tuple[int, str], Dict[int, Dict[str, Mapping[str, str]]]] = {}
    for row in rows:
        algorithm = str(row.get("algorithm_id", ""))
        if algorithm not in ALGORITHM_ORDER:
            continue
        seed = _as_int(row.get("seed"))
        budget = _as_int(row.get("budget"))
        if seed is None or budget is None:
            continue
        mission = str(row.get("mission_label", "unknown"))
        groups.setdefault((budget, mission), {}).setdefault(seed, {})[algorithm] = row
    return groups


def _plot_value(
    row: Mapping[str, str], metric: MetricSpec, budget: int
) -> Tuple[float | None, str | None, float | None]:
    raw_value = _as_float(row.get(metric.key))
    if raw_value is not None:
        label = str(int(round(raw_value))) if metric.integer else f"{raw_value:.3g}"
        return raw_value, label, raw_value
    if metric.censored_at_budget:
        return float(budget + 1), f">{budget}", None
    return None, None, None


def _better_algorithm(random_value: float, tg_value: float, higher_is_better: bool) -> str:
    if math.isclose(random_value, tg_value, rel_tol=1e-12, abs_tol=1e-12):
        return "tie"
    if higher_is_better:
        return TG_ID if tg_value > random_value else RANDOM_ID
    return TG_ID if tg_value < random_value else RANDOM_ID


def _oriented_improvement(random_value: float, tg_value: float, higher_is_better: bool) -> float:
    return tg_value - random_value if higher_is_better else random_value - tg_value


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _write_readme(output_dir: Path, plot_count: int, pair_count: int) -> None:
    text = f"""# Benchmark comparison plots

Generated paired plots: {plot_count}
Paired seed-metric observations: {pair_count}

Each line connects the two algorithms for the same mission, seed, and simulator
budget. With only two seeds, every observation is shown explicitly. The plots do
not display boxplots, confidence intervals, p-values, or claims of statistical
significance.

For metrics marked *higher is better*, an upward line from random search to
TG-MCTS-Elites favours TG-MCTS-Elites. For metrics marked *lower is better*, a
downward line favours TG-MCTS-Elites.

For time-to-first-failure plots, a value shown as `>B` means no official failure
was found within budget `B`; it is plotted at `B + 1` only to keep the censored
observation visible.
"""
    destination = output_dir / "README.md"
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    import os
    os.replace(temporary, destination)


def generate_benchmark_plots(
    raw_runs_path: Path,
    output_dir: Path,
    metrics: Sequence[MetricSpec] = PRIMARY_METRICS,
) -> List[Dict[str, Any]]:
    rows = deduplicate_runs(load_raw_runs(raw_runs_path))
    groups = _paired_groups(rows)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: List[Dict[str, Any]] = []
    differences: List[Dict[str, Any]] = []

    for (budget, mission), by_seed in sorted(groups.items()):
        paired_seeds = [
            seed
            for seed, algorithms in sorted(by_seed.items())
            if all(algorithm in algorithms for algorithm in ALGORITHM_ORDER)
        ]
        if not paired_seeds:
            continue

        mission_dir = output_dir / f"budget_{budget:03d}" / _slug(mission)
        mission_dir.mkdir(parents=True, exist_ok=True)

        for metric in metrics:
            plotted_pairs: List[Tuple[int, float, float, str, str, float | None, float | None]] = []
            for seed in paired_seeds:
                algorithms = by_seed[seed]
                random_plot, random_label, random_raw = _plot_value(
                    algorithms[RANDOM_ID], metric, budget
                )
                tg_plot, tg_label, tg_raw = _plot_value(
                    algorithms[TG_ID], metric, budget
                )
                if random_plot is None or tg_plot is None:
                    continue
                plotted_pairs.append(
                    (
                        seed,
                        random_plot,
                        tg_plot,
                        random_label or "",
                        tg_label or "",
                        random_raw,
                        tg_raw,
                    )
                )

            if not plotted_pairs:
                continue

            figure, axis = plt.subplots(figsize=(7.4, 5.2))
            for seed, random_plot, tg_plot, random_label, tg_label, _, _ in plotted_pairs:
                line = axis.plot(
                    [0, 1],
                    [random_plot, tg_plot],
                    marker="o",
                    linewidth=1.7,
                    markersize=6,
                    label=f"Seed {seed}",
                )[0]
                axis.annotate(
                    random_label,
                    (0, random_plot),
                    xytext=(-8, 5),
                    textcoords="offset points",
                    ha="right",
                    fontsize=8,
                    color=line.get_color(),
                )
                axis.annotate(
                    tg_label,
                    (1, tg_plot),
                    xytext=(8, 5),
                    textcoords="offset points",
                    ha="left",
                    fontsize=8,
                    color=line.get_color(),
                )

            direction = "higher is better" if metric.higher_is_better else "lower is better"
            axis.set_title(
                f"{metric.label} — {mission}\n"
                f"Budget {budget}; {len(plotted_pairs)} paired seed(s); {direction}"
            )
            axis.set_xticks([0, 1], [ALGORITHM_LABELS[RANDOM_ID], ALGORITHM_LABELS[TG_ID]])
            axis.set_xlim(-0.25, 1.25)
            axis.set_ylabel(metric.axis_label)
            axis.grid(axis="y", alpha=0.25)
            if metric.percentage:
                axis.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
                axis.set_ylim(bottom=0.0)
            elif metric.censored_at_budget:
                axis.set_ylim(0.0, budget + 1.8)
                axis.axhline(budget, linestyle="--", linewidth=1.0, alpha=0.5)
            elif metric.key == "best_min_distance":
                axis.set_ylim(bottom=0.0)
            if metric.integer and not metric.censored_at_budget:
                lower, upper = axis.get_ylim()
                axis.set_ylim(math.floor(min(0.0, lower)), math.ceil(upper + 0.25))
            axis.legend(loc="best", title="Paired observations", fontsize=8)
            figure.tight_layout()

            plot_path = mission_dir / f"{metric.key}.png"
            temporary_plot = plot_path.with_name(plot_path.stem + ".tmp.png")
            figure.savefig(temporary_plot, dpi=180, format="png")
            plt.close(figure)
            import os
            os.replace(temporary_plot, plot_path)

            manifest.append(
                {
                    "budget": budget,
                    "mission_label": mission,
                    "metric": metric.key,
                    "metric_label": metric.label,
                    "direction": direction,
                    "paired_seed_count": len(plotted_pairs),
                    "seeds": "|".join(str(item[0]) for item in plotted_pairs),
                    "plot_file": str(plot_path.resolve()),
                }
            )

            for seed, random_plot, tg_plot, _, _, random_raw, tg_raw in plotted_pairs:
                comparison_random = random_plot if random_raw is None else random_raw
                comparison_tg = tg_plot if tg_raw is None else tg_raw
                differences.append(
                    {
                        "budget": budget,
                        "mission_label": mission,
                        "seed": seed,
                        "metric": metric.key,
                        "direction": direction,
                        "random_search_value": random_raw,
                        "tg_mcts_elites_value": tg_raw,
                        "random_search_plot_value": random_plot,
                        "tg_mcts_elites_plot_value": tg_plot,
                        "oriented_improvement_tg_minus_random": _oriented_improvement(
                            comparison_random,
                            comparison_tg,
                            metric.higher_is_better,
                        ),
                        "better_algorithm": _better_algorithm(
                            comparison_random,
                            comparison_tg,
                            metric.higher_is_better,
                        ),
                    }
                )

    _write_csv(manifest, output_dir / "plot_manifest.csv")
    _write_csv(differences, output_dir / "paired_differences.csv")
    _write_readme(output_dir, len(manifest), len(differences))
    return manifest


def main() -> int:
    args = parse_args()
    try:
        manifest = generate_benchmark_plots(args.raw_runs, args.output_dir)
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Benchmark plotting failed: {error}")
        return 1
    if not manifest:
        print(
            "No complete TG-MCTS-Elites/random-search seed pairs were found. "
            "Run both algorithms with the same mission, seed, and budget first."
        )
        return 1
    print(f"Plots generated: {len(manifest)}")
    print(f"Plot directory: {args.output_dir}")
    print(f"Manifest: {args.output_dir / 'plot_manifest.csv'}")
    print(f"Paired differences: {args.output_dir / 'paired_differences.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
