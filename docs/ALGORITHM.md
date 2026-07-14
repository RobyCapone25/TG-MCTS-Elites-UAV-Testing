# TG-MCTS-Elites Algorithm

## 1. Search objective

The generator searches for valid obstacle configurations that minimize the minimum UAV-obstacle distance while preserving competition input compliance. Mission completion is recorded as an execution outcome, not used to invalidate an otherwise valid simulated test.

The official point function is

\[
p(d)=
\begin{cases}
5, & d<0.25,\\
2, & 0.25\le d<1.0,\\
1, & 1.0\le d<1.5,\\
0, & d\ge 1.5.
\end{cases}
\]

An official distance failure satisfies \(d<1.5\,\mathrm{m}\). The label `critical_proximity` below 0.25 m is a distance classification, not independent collision evidence. A non-completed mission close to an obstacle is retained and labelled with explicit evidence such as `noncompleted_critical_proximity`; it is not called a confirmed collision.

## 2. Mission-derived reference path

The case-study YAML is inspected recursively for its `mission_file`. The referenced QGroundControl `.plan` is converted from latitude/longitude to a local metric path.

Because the competition simulator frame may differ by axis order or sign from geographic ENU, the implementation evaluates eight candidate mappings:

```text
east_north, east_south, west_north, west_south,
north_east, north_west, south_east, south_west
```

The selected mapping maximizes intersection with the legal obstacle-generation area. Initial scenarios and path-oriented mutations are sampled from this inferred mission path rather than from mission-name-specific constants.

## 3. Scenario representation and constraints

A scenario contains at most three rotated rectangular obstacles. Each obstacle is described by

\[
(x,y,z,r,l,w,h),
\]

where \((x,y,z)\) is the position, \(r\) the yaw rotation, and \((l,w,h)\) the box dimensions.

Validation checks:

- numerical parameter bounds;
- `z = 0`;
- rotated corners inside the legal domain;
- pairwise non-overlap using the separating-axis theorem;
- a grid-based free-space corridor along the mission path.

## 4. Mission-guided scenario operators

Initialization operators are:

- `init_single`: one blocker near the mission path;
- `init_gate`: two obstacles forming a narrow passage;
- `init_staggered`: two or three alternating obstacles along the path.

Mutation operators are:

- `mutate_local`;
- `mutate_strong`;
- `slide_y` (implemented as motion along the inferred mission tangent);
- `resize`;
- `rotate`;
- `tighten_gate`;
- `add_blocker`.

## 5. Monte Carlo Tree Search

Each MCTS node stores one obstacle configuration. Selection uses

\[
\operatorname{UCB}(c)=
\frac{R_c}{N_c}
+C\sqrt{\frac{\log(N_p+1)}{N_c}},
\]

where \(R_c\) and \(N_c\) are the child cumulative reward and visit count, and \(N_p\) is the parent visit count.

Progressive widening limits the number of children:

\[
|\mathcal C(n)| < \max\left(1,\left\lfloor C_{pw}(N_n+1)^{\alpha}\right\rfloor\right).
\]

After each evaluated simulation, the reward is backpropagated to every ancestor.

## 6. MAP-Elites archive

The behavior descriptor is

```text
(number of obstacles,
 mean-x bin,
 mean-y bin,
 compactness bin,
 mean-rotation bin)
```

Each cell retains the candidate with the best search-time quality key. This archive promotes behavioral coverage during the search but does not directly define the final returned suite.

## 7. Reward

The implemented reward is

\[
R = 25p(d) + \frac{5}{0.2+d} + \frac{4}{n_o} + b_m - 0.05t,
\]

where:

- \(p(d)\) is the official point;
- \(n_o\) is the number of obstacles;
- \(t\) is elapsed simulation time in minutes;
- \(b_m=3\) for a completed mission and \(0.5\) when completion is unknown.

The reward favors official failures, smaller distance, simpler scenarios, completed missions when all else is equal, and lower runtime. Non-completed executions still receive their distance-based failure reward and therefore guide MCTS.

## 8. Strict simulator-attempt budget

Every real simulator execution consumes one unit, including:

- successful evaluations;
- executions later rejected as non-compliant;
- system-error retries;
- confirmation reruns.

Pre-execution invalid candidates do not consume budget because the simulator is not called.

## 9. Failure-artifact policy

All evaluated runs retain lightweight metadata. Heavy YAML, ULG, and plot artifacts are kept when the input is compliant and the execution satisfies \(d<1.5\,\mathrm{m}\), regardless of whether the mission completed. Thus a collision-like non-completion does not lose its evidence.

The generated plots are:

- `trajectory_overview.png`: \(X(t)\), \(Y(t)\), \(Z(t)\), and the planar \(X-Y\) trajectory;
- `trajectory_xy_time.png`: the three-dimensional \((X,Y,t)\) trajectory.

## 10. Execution outcome and failure evidence

Candidate compliance and execution outcome are separate concepts. A legal obstacle configuration can produce any of the following mission outcomes:

- `completed`;
- `not_completed`;
- `unknown`.

The additional `failure_evidence` value explains what was observed without overstating it:

- `critical_proximity`;
- `official_proximity`;
- `noncompleted_critical_proximity`;
- `noncompleted_official_proximity`;
- `noncompleted_without_official_proximity`;
- `unknown_completion`;
- `none`.

A non-completed official proximity result is stored, scored, backpropagated through MCTS, and eligible for confirmation. Only an independent simulator or flight-stack collision signal would justify a future `confirmed_collision` label.

## 11. Confirmation phase

For sufficiently large budgets, a fraction of the total budget is reserved for rerunning leading failures. Each confirmation observation updates:

- point samples;
- minimum-distance samples;
- elapsed-time samples;
- failure reproducibility.

A reproduced official failure keeps its own failure artifacts. A non-failure confirmation keeps metadata only.

## 12. Robust final ranking

The robust ranking key prioritizes:

1. mean official point;
2. failure reproducibility;
3. number of observations;
4. smaller mean minimum distance;
5. fewer obstacles;
6. lower mean elapsed time;
7. initial search reward.

A candidate is returnable only when it is:

- an official distance failure;
- input-compliant;
- classified as either `completed` or `not_completed`;
- artifact-backed;
- at least 50% reproducible under the available observations.

`unknown` mission completion remains excluded. A `not_completed` execution is eligible only because it already satisfies the official proximity threshold; the implementation does not infer a confirmed collision from distance alone.

## 13. Final diversity

Two selected failures are considered too similar when either condition holds:

- normalized, permutation-invariant obstacle distance is below `0.12`;
- normalized Dynamic Time Warping distance between realized XY trajectories is below `0.03`.

This prevents the final suite from containing scenarios that differ only superficially or produce essentially identical UAV behavior.
