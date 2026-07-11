#!/usr/bin/env python3
"""Genera plot in stile ufficiale (come il README di aerialist) per i test salvati:
a sinistra X / Y / Z / Yaw nel tempo, a destra la vista dall'alto X-Y con la
traiettoria e gli ostacoli disegnati come rettangoli grigi ruotati.

Uso:
    python3 plot_official.py generated_tests/2026-06-20-12-59-08/    # tutta la cartella
    python3 plot_official.py generated_tests/.../test_0.yaml         # un singolo test

Per ogni test_N (coppia test_N.yaml + test_N.ulg) salva test_N_plot.png accanto.
Legge la traiettoria con pyulog (host) o, in fallback, con aerialist (dentro Docker).
"""
import glob
import os
import sys

import numpy as np
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def read_trajectory(ulg_path):
    """Ritorna (t, x, y, z, yaw) della traiettoria, allineata all'origine come aerialist.
    t in secondi, z = quota (positiva verso l'alto)."""
    try:
        import pyulog
        ulog = pyulog.ULog(ulg_path, ["vehicle_local_position"])
        d = ulog.get_dataset("vehicle_local_position").data
        t = np.array(d["timestamp"], dtype=float)
        x = np.array(d["x"], dtype=float)
        y = np.array(d["y"], dtype=float)
        z = np.array(d["z"], dtype=float)
        yaw = np.array(d.get("heading", np.zeros_like(x)), dtype=float)
        return (t - t[0]) / 1e6, x - x[0], y - y[0], -z, yaw
    except Exception:
        # fallback: aerialist (disponibile solo dentro l'immagine Docker)
        from aerialist.px4.trajectory import Trajectory
        traj = Trajectory.extract_from_log(ulg_path)
        p = traj.positions
        t = np.array([q.timestamp for q in p], dtype=float)
        return (
            (t - t[0]) / 1e6,
            np.array([q.x for q in p]),
            np.array([q.y for q in p]),
            np.array([q.z for q in p]),
            np.array([q.r for q in p]),
        )


def read_obstacles(yaml_path):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    return data.get("simulation", {}).get("obstacles", []) or []


def obstacle_patch(o):
    """Rettangolo grigio ruotato attorno al centro (come Obstacle.plt_patch di aerialist)."""
    s, p = o["size"], o["position"]
    l, w = float(s["l"]), float(s["w"])
    cx, cy, r = float(p["x"]), float(p["y"]), float(p.get("r", 0))
    return mpatches.Rectangle(
        (cx - l / 2, cy - w / 2), l, w, angle=r, rotation_point="center",
        edgecolor="dimgray", facecolor="gray", alpha=0.5,
    )


def plot_one(ulg_path, yaml_path, out_png, title=""):
    t, x, y, z, yaw = read_trajectory(ulg_path)
    obstacles = read_obstacles(yaml_path)

    fig = plt.figure(figsize=(11, 6))
    gs = fig.add_gridspec(4, 4, hspace=0.35, wspace=0.4)
    ax_x = fig.add_subplot(gs[0, :2])
    ax_y = fig.add_subplot(gs[1, :2])
    ax_z = fig.add_subplot(gs[2, :2])
    ax_r = fig.add_subplot(gs[3, :2])
    ax_xy = fig.add_subplot(gs[:, 2:])

    for ax, series, lab in (
        (ax_x, x, "X (m)"), (ax_y, y, "Y (m)"),
        (ax_z, z, "Z (m)"), (ax_r, yaw, "Yaw (rad)"),
    ):
        ax.plot(t, series, color="#1f4e8c", linewidth=1.4)
        ax.set_ylabel(lab)
    ax_r.set_xlabel("tempo (s)")
    for ax in (ax_x, ax_y, ax_z):
        ax.tick_params(labelbottom=False)

    # vista dall'alto: ostacoli sotto, traiettoria sopra
    for i, o in enumerate(obstacles):
        patch = obstacle_patch(o)
        if i == 0:
            patch.set_label("ostacolo")
        ax_xy.add_patch(patch)
    ax_xy.plot(x, y, color="#1f4e8c", linewidth=1.6, label="traiettoria")
    ax_xy.plot(x[0], y[0], "o", color="green", markersize=8, label="start")
    ax_xy.plot(x[-1], y[-1], "s", color="red", markersize=8, label="end")
    ax_xy.set_xlabel("X (m)")
    ax_xy.set_ylabel("Y (m)")
    ax_xy.yaxis.set_label_position("right")
    ax_xy.yaxis.tick_right()
    ax_xy.set_aspect("equal", "datalim")
    ax_xy.legend(loc="upper right", fontsize=8, framealpha=0.9)

    if title:
        fig.suptitle(title, fontsize=13)
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  {os.path.basename(out_png)}  ({len(obstacles)} ostacolo/i)")


def collect_targets(args):
    targets = []
    for a in args:
        if os.path.isdir(a):
            for yml in sorted(glob.glob(os.path.join(a, "test_*.yaml"))):
                ulg = yml[:-5] + ".ulg"
                if os.path.exists(ulg):
                    targets.append((ulg, yml))
        elif a.endswith(".yaml"):
            ulg = a[:-5] + ".ulg"
            if os.path.exists(ulg):
                targets.append((ulg, a))
    return targets


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    targets = collect_targets(argv)
    if not targets:
        print("Nessuna coppia test_*.yaml + test_*.ulg trovata nei percorsi dati.",
              file=sys.stderr)
        return 1
    print(f"Genero {len(targets)} plot:")
    for ulg, yml in targets:
        out = yml[:-5] + "_plot.png"
        plot_one(ulg, yml, out, title=os.path.basename(yml)[:-5])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
