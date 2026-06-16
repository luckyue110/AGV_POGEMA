from warehouse.layouts import create_default_warehouse_layout
from warehouse.planner import plan_scheduled_paths
from warehouse.scheduler import schedule_tasks_greedy
from warehouse_simulation import (
    build_tasks_from_args,
    build_pogema_targets,
    format_locations,
    format_route_plan,
)


class Args:
    def __init__(self, tasks=None, random_tasks=None, seed=42):
        self.tasks = tasks
        self.random_tasks = random_tasks
        self.seed = seed


def test_build_tasks_from_specified_args():
    layout = create_default_warehouse_layout()
    args = Args(tasks="S1:OUTBOUND,S2:PACKING", random_tasks=None)

    tasks = build_tasks_from_args(args, layout)

    assert [task.pickup_name for task in tasks] == ["S1", "S2"]
    assert [task.dropoff_name for task in tasks] == ["OUTBOUND", "PACKING"]


def test_build_tasks_defaults_to_small_random_set():
    layout = create_default_warehouse_layout()
    args = Args(tasks=None, random_tasks=None, seed=42)

    tasks = build_tasks_from_args(args, layout)

    assert len(tasks) == 4


def test_format_locations_includes_pickups_and_dropoffs():
    layout = create_default_warehouse_layout()

    output = format_locations(layout)

    assert "Pickup points:" in output
    assert "Dropoff points:" in output
    assert "S1" in output
    assert "OUTBOUND" in output


def test_format_route_plan_shows_segment_distances():
    layout = create_default_warehouse_layout()
    tasks = build_tasks_from_args(Args(tasks="S1:OUTBOUND", seed=42), layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    output = format_route_plan(layout.map, schedule, paths)

    assert "AGV" in output
    assert "T001" in output
    assert "S1" in output
    assert "OUTBOUND" in output
    assert "planned_edges=" in output
    assert "operation_wait_edges=" in output
    assert "avoidance_edges=" in output


def test_pogema_targets_follow_last_dropoff_when_paths_return_home():
    layout = create_default_warehouse_layout(num_agvs=2)
    tasks = build_tasks_from_args(Args(tasks="S1:OUTBOUND,S2:PACKING", seed=42), layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(
        layout.map,
        schedule.agv_schedules,
        parking_goals=layout.agv_starts,
        fallback_parking_goals=layout.parking_points,
    )

    targets = build_pogema_targets(layout, schedule)

    assert [path[-1] for path in paths] == layout.agv_starts
    for agv_schedule, target, start in zip(
        schedule.agv_schedules, targets, layout.agv_starts
    ):
        if agv_schedule.tasks:
            assert target == agv_schedule.tasks[-1].dropoff
            assert target != start
