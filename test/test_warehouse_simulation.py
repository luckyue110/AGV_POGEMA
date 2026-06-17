from warehouse.layouts import create_default_warehouse_layout
from warehouse.planner import plan_scheduled_paths
from warehouse.scheduler import schedule_tasks_greedy
from warehouse_simulation import (
    build_buffer_points_from_args,
    build_effective_dispatch_gap,
    build_parking_goals,
    build_pogema_output_names,
    build_tasks_from_args,
    build_pogema_targets,
    build_parser,
    build_route_map_path,
    build_solution_animation_path,
    format_locations,
    format_route_plan,
    parse_buffer_points,
)


class Args:
    def __init__(
        self,
        tasks=None,
        random_tasks=None,
        seed=42,
        buffer_points=None,
        dispatch_gap=4,
        dispatch_policy="fixed",
        parking_policy="home",
    ):
        self.tasks = tasks
        self.random_tasks = random_tasks
        self.seed = seed
        self.buffer_points = buffer_points
        self.dispatch_gap = dispatch_gap
        self.dispatch_policy = dispatch_policy
        self.parking_policy = parking_policy


def test_build_tasks_from_specified_args():
    layout = create_default_warehouse_layout()
    args = Args(tasks="S1:OUTBOUND,S2:PACKING", random_tasks=None)

    tasks = build_tasks_from_args(args, layout)

    assert [task.pickup_name for task in tasks] == ["S1", "S2"]
    assert [task.dropoff_name for task in tasks] == ["OUTBOUND", "PACKING"]


def test_parser_accepts_cbs_planner():
    parser = build_parser()

    args = parser.parse_args(["--planner", "cbs"])

    assert args.planner == "cbs"


def test_parser_accepts_ilp_scheduler():
    parser = build_parser()

    args = parser.parse_args(["--scheduler", "ilp"])

    assert args.scheduler == "ilp"


def test_parser_accepts_warehouse_zone_traffic_rules():
    parser = build_parser()

    args = parser.parse_args(["--traffic-rules", "warehouse-zones"])

    assert args.traffic_rules == "warehouse-zones"


def test_parser_accepts_dispatch_and_parking_policies():
    parser = build_parser()

    args = parser.parse_args(["--dispatch-policy", "asap", "--parking-policy", "nearest"])

    assert args.dispatch_policy == "asap"
    assert args.parking_policy == "nearest"


def test_asap_dispatch_policy_uses_zero_artificial_gap():
    args = Args(dispatch_gap=12, dispatch_policy="asap")

    assert build_effective_dispatch_gap(args) == 0


def test_nearest_parking_policy_assigns_unique_goals_without_stealing_other_homes():
    layout = create_default_warehouse_layout(num_agvs=2)
    tasks = build_tasks_from_args(Args(tasks="S1:OUTBOUND,S2:PACKING"), layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    args = Args(parking_policy="nearest")

    parking_goals = build_parking_goals(args, layout, schedule)

    assert len(set(parking_goals)) == len(parking_goals)
    for agv_id, goal in enumerate(parking_goals):
        other_homes = set(layout.parking_points) - {layout.parking_points[agv_id]}
        assert goal not in other_homes


def test_task_end_parking_policy_disables_return_parking():
    layout = create_default_warehouse_layout(num_agvs=2)
    tasks = build_tasks_from_args(Args(tasks="S1:OUTBOUND"), layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    args = Args(parking_policy="task-end")

    assert build_parking_goals(args, layout, schedule) is None


def test_parser_accepts_custom_buffer_points_and_case_output_folder():
    parser = build_parser()

    args = parser.parse_args(
        [
            "--buffer-points",
            "14,0;13,0",
            "--case-name",
            "complex_buffer_gap12",
            "--planner",
            "cbs",
        ]
    )

    assert args.buffer_points == "14,0;13,0"
    assert build_route_map_path(args).endswith(
        "outputs/animations\\complex_buffer_gap12\\cbs\\warehouse_route_map.svg"
    ) or build_route_map_path(args).endswith(
        "outputs/animations/complex_buffer_gap12/cbs/warehouse_route_map.svg"
    )
    assert build_solution_animation_path(args).endswith(
        "warehouse_solution_animated.svg"
    )


def test_cbs_pogema_outputs_use_distinct_names():
    animation_name, enhanced_path = build_pogema_output_names("cbs")

    assert animation_name == "warehouse_agv_cbs"
    assert enhanced_path == "outputs/animations/warehouse_agv_cbs_enhanced.svg"


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
    assert "Default buffer points:" in output
    assert "S1" in output
    assert "OUTBOUND" in output
    assert "B0" in output


def test_custom_buffer_points_parse_and_validate_free_cells():
    layout = create_default_warehouse_layout()

    points = parse_buffer_points("14,0;13,0;14,0", layout)

    assert points == [(14, 0), (13, 0)]


def test_custom_buffer_points_reject_obstacles():
    layout = create_default_warehouse_layout()

    try:
        parse_buffer_points("2,3", layout)
    except ValueError as exc:
        assert "free cell" in str(exc)
    else:
        raise AssertionError("expected obstacle buffer point to fail")


def test_buffer_points_default_to_layout_left_columns():
    layout = create_default_warehouse_layout(num_agvs=4)
    args = Args(buffer_points=None)

    points = build_buffer_points_from_args(args, layout)

    assert points == layout.buffer_points
    assert all(col in (0, 1) for _, col in points)


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
