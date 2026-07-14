class GeneratorConstants:
    """Central numerical configuration for TG-MCTS-Elites."""

    X_MIN = -40.0
    X_MAX = 30.0
    Y_MIN = 10.0
    Y_MAX = 40.0

    MIN_L = 2.0
    MAX_L = 20.0
    MIN_W = 2.0
    MAX_W = 20.0
    MIN_H = 10.1
    MAX_H = 25.0

    MIN_R = 0.0
    MAX_R = 90.0

    MAX_OBSTACLES = 3
    RETURN_LIMIT = 20

    OVERLAP_MARGIN = 0.10
    FEASIBILITY_GRID_STEP = 1.0
    MISSION_COMPLETION_RADIUS = 10.0

    CRITICAL_PROXIMITY_THRESHOLD = 0.25
    FAILURE_THRESHOLD = 1.5
    NEAR_MISS_THRESHOLD = 3.0

    # Backward-compatible alias. This is a score boundary, not collision proof.
    HARD_FAIL_THRESHOLD = CRITICAL_PROXIMITY_THRESHOLD

    UCB_C = 1.4
    PW_C = 2.0
    PW_ALPHA = 0.55

    MAX_SYSTEM_RETRIES = 2
    # Final-suite diversity filters. A candidate is rejected when either its
    # obstacle geometry or its realised flight trajectory is too similar to a
    # previously selected failure.
    FINAL_MIN_SCENARIO_DISTANCE = 0.12
    FINAL_MIN_TRAJECTORY_DTW = 0.03
    TRAJECTORY_DISTANCE_SCALE_M = 100.0
    MAX_DTW_TRAJECTORY_POINTS = 160

    # Budget-aware robustness confirmation. For budgets below the threshold,
    # all attempts remain available for exploration. Larger runs reserve a
    # fraction for rerunning the best discovered failures.
    CONFIRMATION_MIN_BUDGET = 10
    CONFIRMATION_BUDGET_FRACTION = 0.15
    CONFIRMATION_MAX_CANDIDATES = 3
    CONFIRMATION_TARGET_TOTAL_SAMPLES = 5
    MIN_FAILURE_REPRODUCIBILITY = 0.50

    # Refresh tree/progress snapshots during long runs.
    OUTPUT_SNAPSHOT_INTERVAL = 5
