# CBS Planning Result

Date: 2026-06-17

This document records the first CBS implementation result for the standard complex scenario.

## Strategy

Planner:

```text
warehouse/planner.py::plan_scheduled_paths_cbs
```

CBS structure:

1. Build root paths with low-level constrained A* and no inter-agent reservations.
2. Detect the first vertex or swap conflict.
3. Create one child node per conflicting AGV.
4. Add a constraint to the selected AGV.
5. Replan only the constrained AGV.
6. Prioritize CBS nodes by total path cost and then makespan.
7. Return the first conflict-free node.

Low-level constraints:

```text
("vertex", time, position)
("edge", time, from_position, to_position)
```

## Scenario

```text
AGVs: 8
Random tasks: 16
Seed: 23
Max episode steps: 3000
Operation wait: 3
Turn wait: 2
Dispatch gap: 12
Return parking: AGV start cells
Fallback parking: layout parking points
```

## Metrics

```text
Path lengths: [95, 95, 109, 129, 159, 249, 198, 202]
Path edges:   [94, 94, 108, 128, 158, 248, 197, 201]
Makespan:     248
Sum of edges: 1228
Blocked count in POGEMA playback: 0 for every AGV
```

## Output Files

```text
outputs/animations/warehouse_8agv_16tasks_cbs_route_map.svg
outputs/animations/warehouse_8agv_16tasks_cbs_solution.svg
outputs/animations/warehouse_agv_enhanced.svg
outputs/logs/warehouse_agv_20260617_200903.log
```

## Validation

The CBS planner passed:

```text
uv run python -m pytest -q
38 passed
```

The complex CBS simulation completed in 248 steps with zero blocked moves.
