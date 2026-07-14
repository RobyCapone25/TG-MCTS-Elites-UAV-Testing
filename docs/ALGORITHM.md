# TG-MCTS-Elites Algorithm

## 1. Search objective

The generator searches for input-compliant obstacle configurations that expose
unsafe proximity between the UAV and obstacles while preserving scenario
diversity and respecting one strict simulator-attempt budget.

Let \(d\) be the minimum UAV-obstacle distance observed during one simulation.
The implemented official point function is

$$
p(d)=
\begin{cases}
5, & d<0.25,\\
2, & 0.25\le d<1.0,\\
1, & 1.0\le d<1.5,\\
0, & d\ge 1.5.
\end{cases}
$$

Distances are measured in metres. An **official distance failure** satisfies
\(d<1.5\,\mathrm{m}\).

The label `critical_proximity` identifies \(d<0.25\,\mathrm{m}\). It is not
independent proof of collision. Mission completion is recorded separately and
is not used to redefine input compliance.

## 2. Mission-derived reference path

The case-study YAML is searched recursively for `mission_file`. The referenced
QGroundControl `.plan` is parsed and its latitude/longitude waypoints are
converted to a local metric path relative to the planned home position.

The geographic local frame and the simulator frame can differ by axis order and
sign. The implementation evaluates eight deterministic mappings:

```text
east_north, east_south, west_north, west_south,
north_east, north_west, south_east, south_west
```

For each mapping, the path is sampled and scored by:

1. the number of samples inside the legal obstacle domain;
2. the estimated in-domain path length;
3. a proximity penalty for samples outside the domain.

The highest-scoring mapping is retained. The method is independent of mission
file names and is tested on previously unseen northward and southward plans.

## 3. Scenario representation and constraints

A scenario contains at most three rotated rectangular obstacles. Obstacle \(i\)
is represented by

$$
o_i=(x_i,y_i,z_i,r_i,l_i,w_i,h_i),
$$

where \((x_i,y_i,z_i)\) is position, \(r_i\) is yaw in degrees, and
\((l_i,w_i,h_i)\) are box dimensions.

The implemented domain is:

| Parameter | Constraint |
|---|---:|
| \(x\) | \([-40,30]\) m |
| \(y\) | \([10,40]\) m |
| \(z\) | \(0\) m |
| \(l,w\) | \([2,20]\) m |
| \(h\) | \((10,25]\) m |
| \(r\) | \([0,90]\) degrees |
| obstacle count | \(1,2,\) or \(3\) |

Validation includes:

- scalar bounds;
- all rotated corners inside the legal domain;
- pairwise non-overlap using the separating-axis theorem;
- grid-based free-space connectivity along each mission segment crossing the
  legal domain.

Invalid candidates detected before simulator execution do not consume budget.

## 4. Mission-guided scenario operators

Initialization operators are:

- `init_single`: one blocker sampled near the mission path;
- `init_gate`: two obstacles forming a narrow passage;
- `init_staggered`: two or three alternating obstacles along the path.

Mutation operators are:

- `mutate_local`;
- `mutate_strong`;
- `slide_y`;
- `resize`;
- `rotate`;
- `tighten_gate`;
- `add_blocker`.

`slide_y` is a legacy action name. Its implementation moves one obstacle
primarily along the inferred mission tangent, with a smaller lateral
perturbation.

Each mutation is repaired and revalidated before it can be evaluated.

## 5. Monte Carlo Tree Search

Each MCTS node stores an obstacle configuration and the action that produced it.

For a visited child \(c\) of parent \(p\), selection uses

$$
\operatorname{UCB}(c)=
\frac{R_c}{N_c}
+C_{\mathrm{ucb}}
\sqrt{\frac{\log(N_p+1)}{N_c}},
$$

where \(R_c\) is cumulative reward, \(N_c\) is child visit count, and \(N_p\) is
parent visit count. Unvisited children receive infinite UCB score.

Progressive widening permits expansion while

$$
|\mathcal{C}(n)| <
\max\left(
1,
\left\lfloor
C_{\mathrm{pw}}(N_n+1)^{\alpha}
\right\rfloor
\right).
$$

The current constants are

$$
C_{\mathrm{ucb}}=1.4,\qquad
C_{\mathrm{pw}}=2.0,\qquad
\alpha=0.55.
$$

After each evaluated simulation, reward is backpropagated from the evaluated
node to the root.

## 6. MAP-Elites archive

The behavior descriptor is

```text
(number of obstacles,
 mean-x bin,
 mean-y bin,
 compactness bin,
 mean-rotation bin)
```

The spatial coordinates use five bins each, rotation uses four bins, and
compactness uses three categories.

Each cell retains the candidate with the best search-time key:

1. larger official point;
2. observed mission outcome (`completed` or `not_completed`) preferred to
   `unknown`;
3. smaller minimum distance;
4. larger reward;
5. fewer obstacles.

MAP-Elites promotes behavioral coverage during search. It does not directly
define the final returned suite.

## 7. Reward

For minimum distance \(d\), obstacle count \(n_o\), elapsed time \(t\) in
minutes, and mission bonus \(b_m\), the implemented reward is

$$
R(d,n_o,t)=
25p(d)
+\frac{5}{0.2+d}
+\frac{4}{n_o}
+b_m
-0.05t,
$$

with

$$
b_m=
\begin{cases}
3, & \text{mission completed},\\
0.5, & \text{mission outcome unknown},\\
0, & \text{mission not completed}.
\end{cases}
$$

The reward favors official distance failures, smaller distance, simpler
scenarios, completed missions when other factors are equal, and lower runtime.
A non-completed official distance failure still receives its distance-based
score and influences MCTS.

## 8. Strict simulator-attempt budget

Every real simulator invocation consumes one budget unit, including:

- successful evaluated executions;
- system-error attempts;
- retries of the same pending candidate;
- executions later rejected after simulation;
- confirmation reruns.

Pre-execution validation failures do not consume budget.

For budgets of at least 10 attempts, the generator reserves approximately 15%
for confirmation, capped by the remaining total budget. Unused confirmation
budget is returned to exploration.

## 9. Persistence and recovery

Before simulator execution, the current candidate is written to
`checkpoint/pending_candidate.json`. The attempt counter is persisted before
launching the simulator.

Results, history, confirmations, invalid candidates, and system errors are
appended incrementally. An interrupted run can resume the latest incomplete run
for the same case-study basename unless `TG_FORCE_NEW=1` is set.

A resumed numeric budget is interpreted as the total attempt limit, not an
additional allowance.

## 10. Mission outcome and failure evidence

Input compliance, mission outcome, and failure evidence are separate fields.

Mission outcome is one of:

- `completed`;
- `not_completed`;
- `unknown`.

`failure_evidence` is one of:

- `critical_proximity`;
- `official_proximity`;
- `noncompleted_critical_proximity`;
- `noncompleted_official_proximity`;
- `noncompleted_without_official_proximity`;
- `unknown_completion`;
- `none`.

A non-completed official distance failure is retained and can be confirmed. A
non-completed execution outside the official distance threshold is not returned
as an official failure. Only a future independent simulator or flight-stack
collision signal could justify `confirmed_collision`.

## 11. Artifact-retention policy

All evaluated executions retain lightweight metadata. Heavy artifacts are kept
only when the generated input is compliant and \(d<1.5\,\mathrm{m}\).

A retained execution contains:

- `test.yaml`;
- `flight.ulg`;
- `trajectory_overview.png`;
- `trajectory_xy_time.png`.

Safe executions, near misses, and non-completions outside the official distance
threshold keep metadata only; temporary heavy runtime files are removed.

## 12. Confirmation phase

Leading returnable failures are rerun within the same global budget. The
confirmation target is up to five total observations per selected candidate,
with at most three confirmation candidates.

Each observation updates:

- official-point samples;
- minimum-distance samples;
- elapsed-time samples;
- failure reproducibility.

Failure reproducibility is

$$
\rho =
\frac{\#\{j:p_j>0\}}
{\#\{j\}},
$$

where \(p_j\) is the official point observed on sample \(j\).

A confirmation execution that reproduces an official distance failure keeps a
separate artifact folder. A non-failure confirmation keeps metadata only.

## 13. Robust final ranking

The final ranking key prioritizes, in order:

1. larger mean official point;
2. larger failure reproducibility;
3. more observations;
4. smaller mean minimum distance;
5. fewer obstacles;
6. smaller mean elapsed time;
7. larger initial search reward.

A candidate is returnable only when it is:

- an official distance failure;
- input-compliant;
- classified as `completed` or `not_completed`;
- backed by all four required artifacts;
- at least 50% reproducible under the available observations.

`unknown` mission outcome is excluded.

## 14. Final diversity

For candidates with the same number of obstacles, obstacle configurations are
compared using normalized parameter vectors and the minimum
permutation-invariant assignment distance.

Realized XY trajectories are compared using normalized Dynamic Time Warping.

A candidate is considered too similar to a previously selected failure when
either condition holds:

$$
D_{\mathrm{obstacle}} < 0.12
$$

or

$$
D_{\mathrm{trajectory}} < 0.03.
$$

The selected suite is capped at 20 tests.

## 15. Reproducibility boundary

`TG_SEED` controls Python's random choices for scenario generation and MCTS.
It does not guarantee deterministic simulator behavior. PX4, Gazebo, Docker,
operating-system scheduling, and timing may still produce different trajectories
or outcomes for the same generated input.
