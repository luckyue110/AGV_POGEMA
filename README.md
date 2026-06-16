# AGV POGEMA Warehouse Scheduler

A warehouse AGV scheduling and path-planning demo built on top of [POGEMA](https://github.com/AIRI-Institute/pogema). This project extends the original multi-agent path-finding environment into a runnable warehouse scenario with shelves, inbound/packing/outbound stations, multiple AGVs, random or specified transport tasks, pickup/drop-off waiting time, turn cost, return-to-parking behavior, collision avoidance, and SVG visualization.

## Features

- Configurable warehouse layout with shelves, stations, service cells, and AGV parking points.
- Random task generation and explicit task input such as `S1:OUTBOUND,S3:PACKING`.
- Greedy dispatching: each idle AGV receives the nearest available task.
- A* path planning with a space-time reservation table.
- Prioritized replanning for conflict resolution.
- Vertex and edge constraints for collision handling.
- Pickup and drop-off operation wait time, defaulting to `3` time steps.
- Turn wait time, defaulting to `2` time steps when an AGV changes direction.
- Return-to-start parking after all assigned tasks are completed.
- SVG output for original POGEMA animation, enhanced animation, route maps, and solution animation.

## Installation

This project is designed to run with `uv`.

```powershell
uv sync --dev
```

Run the test suite:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run python -m pytest -q
```

## Quick Start

List available shelves, pickup service cells, and drop-off service cells:

```powershell
uv run python warehouse_simulation.py --list-locations
```

Run the default random task scenario:

```powershell
uv run python warehouse_simulation.py
```

Run a larger scenario with 8 AGVs and 16 random transport tasks:

```powershell
uv run python warehouse_simulation.py `
  --agvs 8 `
  --random-tasks 16 `
  --seed 23 `
  --max-episode-steps 3000 `
  --operation-wait 3 `
  --turn-wait 2 `
  --dispatch-gap 12 `
  --route-map outputs/animations/warehouse_8agv_16tasks_route_map.svg `
  --solution-animation outputs/animations/warehouse_8agv_16tasks_solution.svg
```

Run specified tasks:

```powershell
uv run python warehouse_simulation.py --tasks "S1:OUTBOUND,S3:PACKING,S12:INBOUND"
```

## Output Files

Common outputs are written under `outputs/`:

- `outputs/animations/warehouse_agv.svg`: original POGEMA SVG animation.
- `outputs/animations/warehouse_agv_enhanced.svg`: enhanced animation with cargo, pickup points, destinations, and labels.
- `outputs/animations/warehouse_route_map.svg`: static route map.
- `outputs/animations/warehouse_solution_animated.svg`: standalone animated solution view.
- `outputs/logs/warehouse_agv_*.log`: task assignment, path length, blocked count, and run summary.

The most useful file for inspecting the solution is usually:

```text
outputs/animations/warehouse_agv_enhanced.svg
```

## Algorithm Overview

The core implementation lives in `warehouse/planner.py`.

The current planning pipeline is:

1. The scheduler assigns each AGV a task sequence.
2. A single-AGV planner builds a path through:
   - start position to pickup service cell,
   - pickup wait,
   - pickup service cell to drop-off service cell,
   - drop-off wait,
   - final return to the AGV's start/parking cell.
3. A* uses a space-time reservation table to avoid already planned AGVs.
4. After all initial paths are built, the planner scans for conflicts:
   - vertex conflict: two AGVs occupy the same cell at the same time,
   - swap conflict: two AGVs exchange cells in the same time step.
5. Conflicts are converted into constraints:
   - `("vertex", time, position)`
   - `("edge", time, from_position, to_position)`
6. The lower-priority AGV is replanned with the new constraint.
7. If a constrained replan is not feasible, a small local wait is used as a fallback.

This is not a full optimal CBS implementation. It is a practical prioritized planning with replanning approach. It is much better than a wait-only repair strategy for this warehouse demo because it can reroute an AGV instead of repeatedly forcing it to stop.

## How to Customize the Algorithm

### 1. Change Task Assignment

Task assignment is implemented in:

```text
warehouse/scheduler.py
```

Main entry point:

```python
schedule_tasks_greedy(...)
```

The current strategy chooses the earliest available AGV and assigns the nearest remaining task.

Possible extensions:

- Add congestion cost to task selection.
- Add task priority or due time.
- Batch tasks by inbound/outbound waves.
- Replace greedy assignment with a global matching algorithm.

Keep the output compatible with:

```python
ScheduleResult(agv_schedules=[...], unassigned_tasks=[...])
```

That lets the existing planner and visualization pipeline continue to work.

### 2. Change Path Planning

Path planning is implemented in:

```text
warehouse/planner.py
```

Important functions:

- `plan_scheduled_paths(...)`: public planning entry point.
- `_plan_single_agv_path(...)`: builds one AGV's full task path.
- `astar_with_reservations(...)`: A* with reservations and optional constraints.
- `_first_path_collision(...)`: detects vertex and swap conflicts.
- `_resolve_path_collisions(...)`: prioritized replanning loop.
- `_constraint_from_collision(...)`: converts a conflict into an agent constraint.

To move toward a full CBS implementation, reuse the existing building blocks:

1. Represent a CBS node as:
   - all AGV paths,
   - per-agent constraints,
   - total solution cost.
2. Pop the lowest-cost node.
3. Detect the first conflict.
4. Split into two child nodes, each constraining one of the conflicting AGVs.
5. Replan only the constrained AGV.
6. Continue until a conflict-free node is found.

The project already includes:

- conflict detection,
- agent-specific constraints,
- constrained A*,
- single-AGV replanning.

### 3. Change the Warehouse Layout

Warehouse geometry is defined in:

```text
warehouse/layouts.py
```

Main entry point:

```python
create_default_warehouse_layout(...)
```

Common customization points:

- `shelf_blocks`: obstacle rectangles representing shelf areas.
- `station_points`: inbound, packing, and outbound station cells.
- `agv_starts`: AGV start and parking cells.
- `shelf_points`: cargo locations on shelf obstacle cells.
- `pickup_points`: service cells where AGVs can pick cargo.
- `dropoff_points`: service cells near station obstacles.

Rules to keep in mind:

- Shelves and station cells are obstacles.
- AGVs should never enter shelf or station cells.
- Pickup and drop-off cells should be adjacent traversable cells.
- More AGVs require enough parking cells and enough aisle capacity.

### 4. Change Visualization

Visualization is implemented in:

```text
warehouse/visualization.py
```

Useful functions:

- `save_route_map_svg(...)`
- `save_solution_animation_svg(...)`
- `save_enhanced_pogema_svg(...)`

Common extensions:

- Change cargo icon style.
- Add more task labels.
- Show AGV intent or next destination.
- Add per-AGV route statistics.
- Customize station and shelf rendering.

The enhanced POGEMA SVG keeps the original AGV circle style and overlays cargo/destination information. Empty AGVs remain as plain AGV circles.

## Testing

Run all tests:

```powershell
uv run python -m pytest -q
```

Planner-specific tests:

```powershell
uv run python -m pytest test/test_warehouse_planner.py -q
```

After changing planning logic, verify:

- no vertex conflicts,
- no swap conflicts,
- all AGVs finish their planned paths,
- POGEMA blocked counts remain `0`,
- no AGV has excessive stop-and-go behavior.

## Project Structure

```text
warehouse/
  layouts.py        # Warehouse map, shelves, stations, parking points
  tasks.py          # Task generation and task parsing
  scheduler.py      # AGV task assignment
  planner.py        # A*, reservations, conflicts, replanning
  visualization.py  # Route maps and SVG animation overlays

warehouse_simulation.py  # CLI entry point
test/                    # pytest suite
outputs/                 # Generated animations and logs
```

## Notes

- The current planner is intended as an engineering demo, not a globally optimal solver.
- `collision_system="soft"` is used so POGEMA animation follows the offline planned paths exactly.
- Actual collision avoidance is handled by `warehouse/planner.py`.
- For larger layouts or more AGVs, consider upgrading prioritized replanning to full CBS or adding congestion-aware task assignment.
