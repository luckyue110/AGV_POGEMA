# Warehouse AGV Scheduler Design

## Goal

Extend the current POGEMA A* baseline into a small warehouse AGV scheduling simulation. The first version should model a realistic warehouse layout, accept random or specified pickup-to-dropoff transport tasks, assign tasks to AGVs, plan each AGV's path with A*, and save logs plus SVG animation output.

## Scope

This design targets an engineering prototype, not a full production platform. It keeps the existing command-line and POGEMA workflow, then adds a warehouse domain layer around it.

In scope:

- A complex warehouse-like map with shelves, aisles, stations, and AGV start positions.
- Pickup-to-dropoff transport tasks.
- Random task generation from valid warehouse locations.
- Specified tasks from command-line input.
- Greedy AGV assignment based on estimated travel distance.
- A* path planning for each AGV through all assigned tasks.
- Priority-based conflict avoidance using time-space reservations.
- Logs and SVG animations under the existing `outputs` directory.
- Focused automated tests for task generation, scheduling, and planning.

Out of scope for the first version:

- Web UI or API service.
- Battery, charging, speed profiles, loading time, or capacity constraints.
- Continuous task arrival while the simulation is already running.
- Dynamic replanning during execution.
- Production warehouse integration protocols.

## Architecture

The current project already has a working baseline:

- `astar_baseline.py` runs POGEMA cases.
- `algorithms/astar.py` provides A* and priority planning.
- `test/cases/map.py` defines small MAPF scenarios.
- `utils/result_saver.py` saves logs and animations.

The warehouse extension will add a new package:

- `warehouse/layouts.py`
  - Owns warehouse map definitions and named locations.
  - Exposes a default complex warehouse layout.
  - Converts layout metadata into `pogema.GridConfig`.

- `warehouse/tasks.py`
  - Defines `TransportTask`.
  - Parses specified task strings.
  - Generates random pickup-to-dropoff tasks from valid named locations.

- `warehouse/scheduler.py`
  - Defines AGV assignment data structures.
  - Implements greedy nearest-available-AGV scheduling.

- `warehouse/planner.py`
  - Plans full AGV routes through assigned tasks.
  - Uses A* to connect `current -> pickup -> dropoff`.
  - Applies priority reservations across AGVs.

- `warehouse_simulation.py`
  - Provides the command-line entry point.
  - Creates layout, tasks, schedule, planned paths, POGEMA config, and output artifacts.

Tests will live under `test/` and follow the existing lightweight style.

## Warehouse Layout

The default layout should look like a small warehouse:

- Shelf blocks are obstacles.
- Main aisles and cross aisles are open cells.
- AGV starts are near a depot or charging zone.
- Pickup locations are named shelf-side cells such as `S1`, `S2`, `S3`.
- Dropoff locations are named stations such as `PACKING`, `OUTBOUND`, and `INBOUND`.

Coordinates use the existing project convention: `(row, col)`.

The layout object should expose:

- `map`: POGEMA-compatible obstacle map where `1` is blocked and `0` is free.
- `agv_starts`: list of AGV start coordinates.
- `pickup_points`: dictionary from name to coordinate.
- `dropoff_points`: dictionary from name to coordinate.
- `all_named_points`: merged lookup for parsing specified tasks.

## Task Model

Each task is a pickup-to-dropoff transport:

```python
TransportTask(
    task_id="T001",
    pickup_name="S1",
    pickup=(2, 3),
    dropoff_name="OUTBOUND",
    dropoff=(13, 18),
)
```

Specified task format:

```text
S1:OUTBOUND,S3:PACKING
```

This creates two tasks:

- pickup `S1`, dropoff `OUTBOUND`
- pickup `S3`, dropoff `PACKING`

Random generation chooses pickup names from shelf-side pickup points and dropoff names from station points. A pickup and dropoff must both be valid free cells.

## Scheduling Algorithm

The scheduler uses a greedy nearest-available-AGV strategy:

1. Keep an estimated current position for each AGV.
2. For each task in queue order, estimate the route cost for every AGV:
   - current AGV position to pickup
   - pickup to dropoff
3. Assign the task to the AGV with the lowest reachable cost.
4. Update that AGV's estimated current position to the task dropoff.
5. If no AGV can reach a task, mark the task unassigned and continue.

This strategy is intentionally simple and explainable. It is a baseline that can later be replaced by auction scheduling, Hungarian assignment, rolling horizon planning, or conflict-aware task allocation.

## Path Planning

The planner builds executable AGV paths after scheduling:

1. For each AGV, start from its initial position.
2. For each assigned task, append:
   - A* path from current position to pickup.
   - A* path from pickup to dropoff.
3. Use time-space reservations so later AGVs avoid earlier AGVs.
4. Reserve the final cell after route completion to avoid another AGV occupying the same endpoint.

The planner may reuse functions from `algorithms/astar.py`, but it should expose warehouse-specific functions so the simulation script does not need to know the low-level reservation details.

## Simulation Flow

`warehouse_simulation.py` should support:

```bash
python warehouse_simulation.py --random-tasks 8 --seed 42
python warehouse_simulation.py --tasks "S1:OUTBOUND,S3:PACKING"
python warehouse_simulation.py --list-locations
```

Run flow:

1. Load default warehouse layout.
2. Build tasks from CLI options.
3. Schedule tasks to AGVs.
4. Plan AGV paths.
5. Convert paths to POGEMA actions.
6. Execute simulation.
7. Save logs to `outputs/logs`.
8. Save SVG animation to `outputs/animations/warehouse_agv.svg`.

## Error Handling

- Unknown pickup or dropoff names should produce a clear command-line error.
- Unreachable task segments should be reported in the log and excluded from executable paths.
- If no tasks are provided, the script should generate a small default random task set.
- If a route cannot be planned for one AGV, other AGVs should still be simulated where possible.

## Testing

Focused tests should cover:

- Default layout contains free AGV starts, pickup points, and dropoff points.
- Random task generation only uses valid named points.
- Specified tasks parse correctly.
- Invalid task names raise clear errors.
- Greedy scheduling assigns a task to the nearest AGV in a controlled map.
- Warehouse path planning creates a path that includes pickup and dropoff.
- The simulation can run a small deterministic case without crashing.

The first version does not need exhaustive performance or optimization tests.

## Acceptance Criteria

- A user can run a warehouse simulation from the command line.
- The simulation supports both random and specified pickup-to-dropoff tasks.
- The output logs show task assignment, path length, blocked counts, and completion status.
- The output SVG animation shows AGVs moving in the warehouse layout.
- Automated tests pass for the new warehouse modules.
