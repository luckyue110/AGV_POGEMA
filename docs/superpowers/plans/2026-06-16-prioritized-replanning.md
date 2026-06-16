# Prioritized Replanning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current collision repair that only inserts waits with prioritized planning plus per-agent replanning, reducing excessive stop-and-go behavior while preserving collision-free AGV paths.

**Architecture:** Keep `warehouse/planner.py` as the public planning API, but split collision and constraint concepts into small helper functions inside the same module to avoid a broad refactor. The planner will generate initial task paths, detect vertex/swap conflicts, add constraints to the lower-priority AGV, and replan that AGV path with time-aware A* instead of repeatedly inserting waits along the existing path.

**Tech Stack:** Python 3.11, pytest, existing warehouse scheduler/layout/task modules, existing A* implementation in `warehouse/planner.py`.

---

## File Structure

- Modify `warehouse/planner.py`
  - Add conflict representation helpers.
  - Add per-agent constraint table support.
  - Add a replanning loop that replaces `_resolve_path_collisions`.
  - Keep `plan_scheduled_paths(...)` public signature stable unless a small optional tuning argument is needed.
- Modify `test/test_warehouse_planner.py`
  - Add focused tests for conflict detection and constrained A*.
  - Add regression test for the 8 AGV / 16 task case: no collisions and AGV 6 wait count improves.
- Optionally modify `warehouse_simulation.py`
  - Only if the new planner exposes diagnostic metrics that should be logged.

---

### Task 1: Add Path Metrics and Conflict Tests

**Files:**
- Modify: `test/test_warehouse_planner.py`

- [ ] **Step 1: Write failing tests for wait metrics and current regression**

Add these helpers near the existing `_first_collision` helper:

```python
def _wait_steps(path):
    return sum(1 for index in range(1, len(path)) if path[index] == path[index - 1])


def _long_wait_runs(path, minimum=5):
    runs = []
    start = 0
    current = path[0]
    for index, position in enumerate(path[1:], start=1):
        if position != current:
            if index - start >= minimum:
                runs.append((start, index - 1, current, index - start))
            start = index
            current = position
    if len(path) - start >= minimum:
        runs.append((start, len(path) - 1, current, len(path) - start))
    return runs
```

Add this test:

```python
def test_prioritized_replanning_reduces_agv6_stop_and_go_in_complex_case():
    layout = create_default_warehouse_layout(num_agvs=8, max_episode_steps=3000)
    tasks = generate_random_tasks(layout, count=16, seed=23)
    schedule = schedule_tasks_greedy(
        layout.map,
        layout.agv_starts,
        tasks,
        operation_wait=3,
        turn_wait=2,
    )

    paths = plan_scheduled_paths(
        layout.map,
        schedule.agv_schedules,
        operation_wait=3,
        turn_wait=2,
        parking_goals=layout.agv_starts,
        fallback_parking_goals=layout.parking_points,
        dispatch_gap=12,
    )

    assert _first_collision(paths) is None
    assert len(paths[6]) < 260
    assert _wait_steps(paths[6]) < 190
    assert len(_long_wait_runs(paths[6], minimum=10)) < 6
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest test/test_warehouse_planner.py::test_prioritized_replanning_reduces_agv6_stop_and_go_in_complex_case -q
```

Expected: FAIL because current AGV 6 path length is about `434`, wait steps are about `363`, and long wait runs are numerous.

---

### Task 2: Add Agent-Specific Constraint Model

**Files:**
- Modify: `warehouse/planner.py`
- Modify: `test/test_warehouse_planner.py`

- [ ] **Step 1: Write failing tests for constrained A***

Add tests:

```python
def test_astar_respects_vertex_constraint_for_agent():
    grid_map = [[0, 0, 0]]
    constraints = {0: {("vertex", 1, (0, 1))}}

    path = astar_with_reservations(
        grid_map,
        (0, 0),
        (0, 2),
        constraints=constraints,
        agv_id=0,
    )

    assert path == [(0, 0), (0, 0), (0, 1), (0, 2)]


def test_astar_respects_edge_constraint_for_agent():
    grid_map = [[0, 0, 0]]
    constraints = {0: {("edge", 0, (0, 0), (0, 1))}}

    path = astar_with_reservations(
        grid_map,
        (0, 0),
        (0, 2),
        constraints=constraints,
        agv_id=0,
    )

    assert path == [(0, 0), (0, 0), (0, 1), (0, 2)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest test/test_warehouse_planner.py::test_astar_respects_vertex_constraint_for_agent test/test_warehouse_planner.py::test_astar_respects_edge_constraint_for_agent -q
```

Expected: FAIL because `astar_with_reservations` does not accept `constraints`.

- [ ] **Step 3: Implement minimal constraint checks**

In `warehouse/planner.py`, add type aliases:

```python
VertexConstraint = tuple[str, int, Coordinate]
EdgeConstraint = tuple[str, int, Coordinate, Coordinate]
Constraint = VertexConstraint | EdgeConstraint
ConstraintTable = dict[int, set[Constraint]]
```

Change `astar_with_reservations` signature:

```python
def astar_with_reservations(
    grid_map: list[list[int]],
    start: Coordinate,
    goal: Coordinate,
    reservations: ReservationTable | None = None,
    start_time: int = 0,
    agv_id: int | None = None,
    constraints: ConstraintTable | None = None,
) -> list[Coordinate] | None:
```

Add helper:

```python
def _violates_constraint(
    constraints: ConstraintTable | None,
    agv_id: int | None,
    current: Coordinate,
    next_pos: Coordinate,
    time: int,
) -> bool:
    if constraints is None or agv_id is None:
        return False
    agent_constraints = constraints.get(agv_id, set())
    return (
        ("vertex", time + 1, next_pos) in agent_constraints
        or ("edge", time, current, next_pos) in agent_constraints
    )
```

Inside the A* neighbor loop, before pushing `next_state`, add:

```python
if _violates_constraint(constraints, agv_id, (row, col), (nr, nc), time):
    continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run the two targeted tests again. Expected: PASS.

---

### Task 3: Extract Replannable Single-AGV Path Builder

**Files:**
- Modify: `warehouse/planner.py`
- Modify: `test/test_warehouse_planner.py`

- [ ] **Step 1: Write a test proving single-agent builder preserves task semantics**

Add test:

```python
def test_single_agv_replan_path_preserves_task_order_and_parking():
    layout = create_default_warehouse_layout(num_agvs=1)
    tasks = generate_random_tasks(layout, count=2, seed=7)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks).agv_schedules[0]

    path = _plan_single_agv_path(
        layout.map,
        schedule,
        operation_wait=3,
        turn_wait=2,
        parking_goal=layout.agv_starts[0],
        fallback_parking_goals=layout.parking_points,
        dispatch_gap=0,
        reservations={},
        constraints={},
    )

    assert path[0] == layout.agv_starts[0]
    for task in schedule.tasks:
        assert task.pickup in path
        assert task.dropoff in path
    assert path[-1] == layout.agv_starts[0]
```

Import `_plan_single_agv_path` from `warehouse.planner`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest test/test_warehouse_planner.py::test_single_agv_replan_path_preserves_task_order_and_parking -q
```

Expected: FAIL because `_plan_single_agv_path` does not exist.

- [ ] **Step 3: Extract implementation from `plan_scheduled_paths`**

Create `_plan_single_agv_path(...)` in `warehouse/planner.py`:

```python
def _plan_single_agv_path(
    grid_map: list[list[int]],
    schedule: AGVSchedule,
    operation_wait: int,
    turn_wait: int,
    parking_goal: Coordinate | None,
    fallback_parking_goals: list[Coordinate],
    dispatch_gap: int,
    reservations: ReservationTable,
    constraints: ConstraintTable,
) -> list[Coordinate]:
    current = schedule.start
    full_path = [current]
    _append_wait(full_path, current, schedule.agv_id * dispatch_gap)

    for task in schedule.tasks:
        to_pickup = astar_with_reservations(
            grid_map,
            current,
            task.pickup,
            reservations,
            len(full_path) - 1,
            agv_id=schedule.agv_id,
            constraints=constraints,
        )
        if to_pickup is None:
            continue
        _extend_with_turn_waits(full_path, to_pickup, turn_wait)
        _append_wait(full_path, task.pickup, operation_wait)
        current = task.pickup

        to_dropoff = astar_with_reservations(
            grid_map,
            current,
            task.dropoff,
            reservations,
            len(full_path) - 1,
            agv_id=schedule.agv_id,
            constraints=constraints,
        )
        if to_dropoff is None:
            continue
        _extend_with_turn_waits(full_path, to_dropoff, turn_wait)
        _append_wait(full_path, task.dropoff, operation_wait)
        current = task.dropoff

    if parking_goal is not None and schedule.tasks:
        to_parking = _find_parking_path(
            grid_map,
            current,
            parking_goal,
            fallback_parking_goals,
            reservations,
            len(full_path) - 1,
            schedule.agv_id,
            constraints,
        )
        if to_parking is not None:
            _extend_with_turn_waits(full_path, to_parking, turn_wait)

    return full_path
```

Update `_find_parking_path` to accept and pass `constraints`.

- [ ] **Step 4: Run test to verify it passes**

Run the targeted test. Expected: PASS.

---

### Task 4: Replace Wait-Only Repair with Prioritized Replanning

**Files:**
- Modify: `warehouse/planner.py`

- [ ] **Step 1: Add conflict-to-constraint helper**

Add:

```python
def _constraint_from_collision(collision, delayed_agv: int) -> Constraint:
    kind = collision[0]
    time = collision[1]
    if kind == "vertex":
        position = collision[4]
        return ("vertex", time, position)

    _, swap_time, first_agv, second_agv, first_from, first_to = collision
    if delayed_agv == first_agv:
        return ("edge", swap_time, first_from, first_to)
    return ("edge", swap_time, first_to, first_from)
```

- [ ] **Step 2: Add reservation rebuild helper**

Add:

```python
def _build_reservations_from_paths(
    paths: list[list[Coordinate]],
    hold_final: bool,
) -> ReservationTable:
    reservations: ReservationTable = {}
    for agv_id, path in enumerate(paths):
        if not path:
            continue
        _reserve_path(reservations, path, agv_id, reserve_final=hold_final)
    return reservations
```

- [ ] **Step 3: Implement prioritized replanning loop**

Replace `_resolve_path_collisions(...)` internals with:

```python
def _resolve_path_collisions(
    paths: list[list[Coordinate]],
    schedules: list[AGVSchedule],
    grid_map: list[list[int]],
    operation_wait: int,
    turn_wait: int,
    parking_goals: list[Coordinate] | None,
    fallback_parking_goals: list[Coordinate],
    dispatch_gap: int,
    max_iterations: int = 200,
    hold_final: bool = False,
) -> list[list[Coordinate]]:
    repaired = [list(path) for path in paths]
    constraints: ConstraintTable = {}

    for _ in range(max_iterations):
        collision = _first_path_collision(repaired, hold_final=hold_final)
        if collision is None:
            return repaired

        delayed_agv = max(collision[2], collision[3])
        constraints.setdefault(delayed_agv, set()).add(
            _constraint_from_collision(collision, delayed_agv)
        )

        reservations = _build_reservations_from_paths(
            [
                path if agv_id != delayed_agv else []
                for agv_id, path in enumerate(repaired)
            ],
            hold_final=hold_final,
        )
        parking_goal = parking_goals[delayed_agv] if parking_goals else None
        replanned = _plan_single_agv_path(
            grid_map,
            schedules[delayed_agv],
            operation_wait,
            turn_wait,
            parking_goal,
            fallback_parking_goals,
            dispatch_gap,
            reservations,
            constraints,
        )
        repaired[delayed_agv] = replanned

    return repaired
```

Update the `plan_scheduled_paths(...)` call site:

```python
return _resolve_path_collisions(
    paths,
    schedules,
    grid_map,
    operation_wait,
    turn_wait,
    parking_goals,
    fallback_parking_goals or [],
    dispatch_gap,
    hold_final=parking_goals is not None,
)
```

- [ ] **Step 4: Run complex regression**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest test/test_warehouse_planner.py::test_prioritized_replanning_reduces_agv6_stop_and_go_in_complex_case -q
```

Expected: PASS or a meaningful remaining failure showing the replanner still needs a better delayed-agent selection policy.

---

### Task 5: Improve Delayed-Agent Selection if Needed

**Files:**
- Modify: `warehouse/planner.py`
- Modify: `test/test_warehouse_planner.py`

- [ ] **Step 1: If Task 4 still fails, write selection test**

Add:

```python
def test_replanner_delays_agent_with_more_remaining_flexibility():
    paths = [
        [(0, 0), (0, 1), (0, 2)],
        [(1, 1), (0, 1), (1, 1), (1, 2)],
    ]
    collision = _first_collision(paths)

    assert _choose_replan_agent(collision, paths) == 1
```

Import `_choose_replan_agent`.

- [ ] **Step 2: Implement heuristic selector**

Add:

```python
def _choose_replan_agent(collision, paths: list[list[Coordinate]]) -> int:
    first_agv = collision[2]
    second_agv = collision[3]
    first_remaining = len(paths[first_agv]) - collision[1]
    second_remaining = len(paths[second_agv]) - collision[1]
    if second_remaining >= first_remaining:
        return second_agv
    return first_agv
```

Use it instead of `max(collision[2], collision[3])`.

- [ ] **Step 3: Run planner tests**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest test/test_warehouse_planner.py -q
```

Expected: PASS.

---

### Task 6: Regenerate Simulation Outputs and Verify

**Files:**
- No source changes unless diagnostics are needed.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Regenerate complex animation**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python warehouse_simulation.py --agvs 8 --random-tasks 16 --seed 23 --max-episode-steps 3000 --operation-wait 3 --turn-wait 2 --dispatch-gap 12 --route-map outputs/animations/warehouse_8agv_16tasks_route_map.svg --solution-animation outputs/animations/warehouse_8agv_16tasks_solution.svg
```

Expected:
- Simulation finishes before `max_episode_steps`.
- All AGV blocked counts are `0`.
- `outputs/animations/warehouse_agv_enhanced.svg` is regenerated.

- [ ] **Step 3: Verify path collision scan**

Run:

```powershell
$env:UV_CACHE_DIR='.uv-cache'; uv run python -c "from warehouse.layouts import create_default_warehouse_layout; from warehouse.tasks import generate_random_tasks; from warehouse.scheduler import schedule_tasks_greedy; from warehouse.planner import plan_scheduled_paths; layout=create_default_warehouse_layout(8,3000); tasks=generate_random_tasks(layout,16,23); sched=schedule_tasks_greedy(layout.map,layout.agv_starts,tasks,operation_wait=3,turn_wait=2); paths=plan_scheduled_paths(layout.map,sched.agv_schedules,operation_wait=3,turn_wait=2,parking_goals=layout.agv_starts,fallback_parking_goals=layout.parking_points,dispatch_gap=12); max_t=max(len(p) for p in paths); print('lens',[len(p) for p in paths]);\nfor t in range(max_t):\n pos={}\n for i,p in enumerate(paths):\n  xy=p[min(t,len(p)-1)]\n  if xy in pos:\n   print('vertex',t,pos[xy],i,xy); raise SystemExit\n  pos[xy]=i\nfor t in range(max_t-1):\n for i,p in enumerate(paths):\n  a=p[min(t,len(p)-1)]; b=p[min(t+1,len(p)-1)]\n  for j,q in enumerate(paths):\n   if i>=j: continue\n   c=q[min(t,len(q)-1)]; d=q[min(t+1,len(q)-1)]\n   if a==d and b==c and a!=b:\n    print('swap',t,i,j,a,b); raise SystemExit\nprint('no vertex/swap conflicts')"
```

Expected: prints `no vertex/swap conflicts`; AGV 6 length should be below the threshold in the regression test.

---

## Self-Review

- Spec coverage: The plan implements prioritized planning with replanning, keeps the public simulation flow intact, and verifies reduced AGV 6 stop-and-go.
- Placeholder scan: No placeholders remain; each task has concrete code and commands.
- Type consistency: `ConstraintTable`, `ReservationTable`, `Coordinate`, and `_plan_single_agv_path` signatures are consistent across tasks.
