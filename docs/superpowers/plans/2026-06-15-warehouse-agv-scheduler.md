# Warehouse AGV Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a command-line warehouse AGV scheduling simulation with random/specified pickup-to-dropoff tasks, greedy assignment, A* path planning, logs, and SVG animation.

**Architecture:** Add a focused `warehouse` package around the existing POGEMA baseline. Keep layout, task generation, scheduling, and path planning isolated, then wire them through a new `warehouse_simulation.py` entry point.

**Tech Stack:** Python, POGEMA, existing A* utilities, `pytest`-style tests or direct Python assertions.

---

### Task 1: Warehouse Layout

**Files:**
- Create: `warehouse/__init__.py`
- Create: `warehouse/layouts.py`
- Test: `test/test_warehouse_layouts.py`

- [ ] **Step 1: Write failing tests**

Create tests that assert the default layout has valid free AGV starts, pickup points, and dropoff points.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest test/test_warehouse_layouts.py -q`
Expected: failure because `warehouse.layouts` does not exist.

- [ ] **Step 3: Implement layout module**

Define `WarehouseLayout`, `create_default_warehouse_layout()`, and `to_grid_config()`.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest test/test_warehouse_layouts.py -q`
Expected: pass.

### Task 2: Task Model and Generation

**Files:**
- Create: `warehouse/tasks.py`
- Test: `test/test_warehouse_tasks.py`

- [ ] **Step 1: Write failing tests**

Test `parse_task_spec()` for specified tasks, invalid names, and `generate_random_tasks()` for valid generated points.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest test/test_warehouse_tasks.py -q`
Expected: failure because `warehouse.tasks` does not exist.

- [ ] **Step 3: Implement task module**

Define `TransportTask`, `parse_task_spec()`, and `generate_random_tasks()`.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest test/test_warehouse_tasks.py -q`
Expected: pass.

### Task 3: Greedy Scheduler

**Files:**
- Create: `warehouse/scheduler.py`
- Test: `test/test_warehouse_scheduler.py`

- [ ] **Step 1: Write failing tests**

Test that a controlled task is assigned to the nearest reachable AGV and that unreachable tasks are recorded.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest test/test_warehouse_scheduler.py -q`
Expected: failure because `warehouse.scheduler` does not exist.

- [ ] **Step 3: Implement scheduler**

Define `AGVSchedule`, `ScheduleResult`, and `schedule_tasks_greedy()`.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest test/test_warehouse_scheduler.py -q`
Expected: pass.

### Task 4: Warehouse Planner

**Files:**
- Create: `warehouse/planner.py`
- Test: `test/test_warehouse_planner.py`

- [ ] **Step 1: Write failing tests**

Test full path planning includes AGV start, pickup, and dropoff, and that action conversion works through existing `path_to_actions()`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest test/test_warehouse_planner.py -q`
Expected: failure because `warehouse.planner` does not exist.

- [ ] **Step 3: Implement planner**

Define `plan_scheduled_paths()` with time-space reservations and helper A* path stitching.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest test/test_warehouse_planner.py -q`
Expected: pass.

### Task 5: Simulation Entry Point

**Files:**
- Create: `warehouse_simulation.py`
- Test: `test/test_warehouse_simulation.py`

- [ ] **Step 1: Write failing tests**

Test argument task creation and a tiny deterministic simulation setup path without requiring visual inspection.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest test/test_warehouse_simulation.py -q`
Expected: failure because `warehouse_simulation.py` does not exist.

- [ ] **Step 3: Implement CLI and simulation orchestration**

Support `--random-tasks`, `--tasks`, `--seed`, and `--list-locations`.

- [ ] **Step 4: Run tests and verify pass**

Run: `python -m pytest test/test_warehouse_simulation.py -q`
Expected: pass.

### Task 6: Full Verification

**Files:**
- Modify only if verification exposes defects.

- [ ] **Step 1: Run all warehouse tests**

Run: `python -m pytest test/test_warehouse_*.py -q`
Expected: all pass.

- [ ] **Step 2: Run a specified-task simulation**

Run: `python warehouse_simulation.py --tasks "S1:OUTBOUND,S3:PACKING" --seed 42`
Expected: exit code 0, log file created, SVG animation created.

- [ ] **Step 3: Run a random-task simulation**

Run: `python warehouse_simulation.py --random-tasks 4 --seed 42`
Expected: exit code 0, log file created, SVG animation created.

## Self-Review

- Spec coverage: layout, tasks, scheduler, planner, CLI, logs, animation, random tasks, and specified tasks are covered.
- Placeholder scan: no open placeholders.
- Type consistency: all planned modules use `WarehouseLayout`, `TransportTask`, `AGVSchedule`, and `ScheduleResult` consistently.
