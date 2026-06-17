import argparse
import os

from utils.result_saver import log_run_summary, save_animation, setup_logger
from warehouse.layouts import WarehouseLayout, create_default_warehouse_layout
from warehouse.planner import path_to_actions, plan_scheduled_paths, plan_scheduled_paths_cbs
from warehouse.scheduler import (
    ScheduleResult,
    schedule_tasks_greedy,
    schedule_tasks_ilp,
    shortest_path_length,
)
from warehouse.tasks import TransportTask, generate_random_tasks, parse_task_spec
from warehouse.traffic import TrafficRules, build_warehouse_zone_traffic_rules
from warehouse.visualization import save_route_map_svg, save_solution_animation_svg
from warehouse.visualization import save_enhanced_pogema_svg


def build_tasks_from_args(args, layout: WarehouseLayout) -> list[TransportTask]:
    if args.tasks:
        return parse_task_spec(args.tasks, layout)

    count = args.random_tasks if args.random_tasks is not None else 4
    return generate_random_tasks(layout, count=count, seed=args.seed)


def build_buffer_points_from_args(
    args, layout: WarehouseLayout
) -> list[tuple[int, int]]:
    if not args.buffer_points:
        return layout.buffer_points
    return parse_buffer_points(args.buffer_points, layout)


def parse_buffer_points(spec: str, layout: WarehouseLayout) -> list[tuple[int, int]]:
    points = []
    for raw_item in spec.split(";"):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 2:
            raise ValueError(
                "buffer points must use row,col pairs separated by semicolons"
            )
        try:
            point = (int(parts[0]), int(parts[1]))
        except ValueError as exc:
            raise ValueError("buffer point coordinates must be integers") from exc
        _validate_buffer_point(point, layout)
        if point not in points:
            points.append(point)

    if not points:
        raise ValueError("at least one buffer point is required")
    return points


def _validate_buffer_point(point: tuple[int, int], layout: WarehouseLayout) -> None:
    row, col = point
    if not (0 <= row < len(layout.map) and 0 <= col < len(layout.map[0])):
        raise ValueError(f"buffer point {point} is outside the warehouse map")
    if layout.map[row][col] != 0:
        raise ValueError(f"buffer point {point} must be on a free cell")


def format_locations(layout: WarehouseLayout) -> str:
    lines = ["Pickup points:"]
    for name, coord in sorted(layout.pickup_points.items()):
        lines.append(f"  {name}: {coord}")
    lines.append("Dropoff points:")
    for name, coord in sorted(layout.dropoff_points.items()):
        lines.append(f"  {name}: {coord}")
    lines.append("Default buffer points:")
    for index, coord in enumerate(layout.buffer_points):
        lines.append(f"  B{index}: {coord}")
    return "\n".join(lines)


def format_route_plan(
    grid_map: list[list[int]],
    schedule: ScheduleResult,
    paths: list[list[tuple[int, int]]],
    operation_wait: int = 3,
) -> str:
    lines = ["Route plan:"]
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        current = agv_schedule.start
        travel_edges = 0
        wait_edges = len(agv_schedule.tasks) * operation_wait * 2
        lines.append(
            f"  AGV {agv_schedule.agv_id}: tasks="
            f"{[task.task_id for task in agv_schedule.tasks]}, "
            f"planned_edges={max(len(path) - 1, 0)}"
        )
        for task in agv_schedule.tasks:
            to_pickup = shortest_path_length(grid_map, current, task.pickup)
            to_dropoff = shortest_path_length(grid_map, task.pickup, task.dropoff)
            if to_pickup is not None:
                travel_edges += to_pickup
            if to_dropoff is not None:
                travel_edges += to_dropoff
            lines.append(
                f"    {task.task_id}: {current} -> {task.pickup_name}{task.pickup} "
                f"({to_pickup} edges), then {task.dropoff_name}{task.dropoff} "
                f"({to_dropoff} edges)"
            )
            current = task.dropoff
        avoidance_edges = max(len(path) - 1, 0) - travel_edges - wait_edges
        lines.append(
            f"    travel_edges={travel_edges}, operation_wait_edges={wait_edges}, "
            f"avoidance_edges={avoidance_edges}"
        )
    return "\n".join(lines)


def build_pogema_targets(
    layout: WarehouseLayout, schedule: ScheduleResult
) -> list[tuple[int, int]]:
    fallback_target = next(iter(layout.dropoff_points.values()))
    targets = []
    for agv_schedule in schedule.agv_schedules:
        if agv_schedule.tasks:
            targets.append(agv_schedule.tasks[-1].dropoff)
        else:
            targets.append(fallback_target)
    return targets


def build_output_directory(args) -> str:
    return os.path.join(args.output_root, args.case_name, args.planner)


def build_route_map_path(args) -> str:
    return args.route_map or os.path.join(
        build_output_directory(args), "warehouse_route_map.svg"
    )


def build_solution_animation_path(args) -> str:
    return args.solution_animation or os.path.join(
        build_output_directory(args), "warehouse_solution_animated.svg"
    )


def build_pogema_output_names(
    planner_name: str, output_dir: str = "outputs/animations"
) -> tuple[str, str]:
    suffix = "_cbs" if planner_name == "cbs" else ""
    animation_name = f"warehouse_agv{suffix}"
    output_dir = output_dir.rstrip("/\\")
    enhanced_path = f"{output_dir}/warehouse_agv{suffix}_enhanced.svg"
    return animation_name, enhanced_path


def build_effective_dispatch_gap(args) -> int:
    if args.dispatch_policy == "asap":
        return 0
    return args.dispatch_gap


def build_parking_goals(
    args, layout: WarehouseLayout, schedule: ScheduleResult
) -> list[tuple[int, int]] | None:
    if args.parking_policy == "task-end":
        return None
    if args.parking_policy == "home":
        return layout.agv_starts
    if args.parking_policy != "nearest":
        raise ValueError(f"unknown parking policy: {args.parking_policy}")

    assigned = []
    used = set()
    for agv_schedule in schedule.agv_schedules:
        own_home = layout.parking_points[agv_schedule.agv_id]
        candidates = _unique_points([own_home, *layout.buffer_points])
        origin = (
            agv_schedule.tasks[-1].dropoff
            if agv_schedule.tasks
            else agv_schedule.start
        )
        goal = _nearest_unused_point(layout.map, origin, candidates, used)
        assigned.append(goal if goal is not None else agv_schedule.start)
        used.add(assigned[-1])
    return assigned


def build_fallback_parking_goals(
    args, layout: WarehouseLayout
) -> list[tuple[int, int]]:
    if args.parking_policy in ("nearest", "task-end"):
        return []
    return _unique_points([*layout.parking_points, *layout.buffer_points])


def _unique_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unique = []
    seen = set()
    for point in points:
        if point not in seen:
            unique.append(point)
            seen.add(point)
    return unique


def _nearest_unused_point(
    grid_map: list[list[int]],
    origin: tuple[int, int],
    candidates: list[tuple[int, int]],
    used: set[tuple[int, int]],
) -> tuple[int, int] | None:
    best = None
    for index, candidate in enumerate(candidates):
        if candidate in used:
            continue
        distance = shortest_path_length(grid_map, origin, candidate)
        if distance is None:
            continue
        score = (distance, index)
        if best is None or score < best[0]:
            best = (score, candidate)
    return None if best is None else best[1]


def build_traffic_rules_from_args(
    args, layout: WarehouseLayout
) -> TrafficRules | None:
    if args.traffic_rules == "none":
        return None
    if args.traffic_rules == "warehouse-zones":
        return build_warehouse_zone_traffic_rules(layout)
    raise ValueError(f"unknown traffic rules: {args.traffic_rules}")


def build_schedule(args, layout: WarehouseLayout, tasks: list[TransportTask]) -> ScheduleResult:
    traffic_rules = build_traffic_rules_from_args(args, layout)
    dispatch_gap = build_effective_dispatch_gap(args)
    if args.scheduler == "ilp":
        return schedule_tasks_ilp(
            layout.map,
            layout.agv_starts,
            tasks,
            operation_wait=args.operation_wait,
            turn_wait=args.turn_wait,
            parking_goals=layout.agv_starts,
            fallback_parking_goals=layout.parking_points,
            dispatch_gap=dispatch_gap,
            staging_goals=build_buffer_points_from_args(args, layout),
            traffic_rules=traffic_rules,
        )
    return schedule_tasks_greedy(
        layout.map,
        layout.agv_starts,
        tasks,
        operation_wait=args.operation_wait,
        turn_wait=args.turn_wait,
    )


def run_warehouse_simulation(args) -> None:
    layout = create_default_warehouse_layout(
        num_agvs=args.agvs, max_episode_steps=args.max_episode_steps
    )

    if args.list_locations:
        print(format_locations(layout))
        return

    staging_goals = build_buffer_points_from_args(args, layout)
    traffic_rules = build_traffic_rules_from_args(args, layout)
    dispatch_gap = build_effective_dispatch_gap(args)
    tasks = build_tasks_from_args(args, layout)
    schedule = build_schedule(args, layout, tasks)
    parking_goals = build_parking_goals(args, layout, schedule)
    planner = plan_scheduled_paths_cbs if args.planner == "cbs" else plan_scheduled_paths
    paths = planner(
        layout.map,
        schedule.agv_schedules,
        operation_wait=args.operation_wait,
        turn_wait=args.turn_wait,
        parking_goals=parking_goals,
        fallback_parking_goals=build_fallback_parking_goals(args, layout),
        dispatch_gap=dispatch_gap,
        staging_goals=staging_goals,
        traffic_rules=traffic_rules,
    )
    route_map_path = save_route_map_svg(
        layout, tasks, schedule, paths, build_route_map_path(args)
    )
    animation_path = save_solution_animation_svg(
        layout, tasks, schedule, paths, build_solution_animation_path(args)
    )
    print(f"Route map saved: {route_map_path}")
    print(f"Solution animation saved: {animation_path}")
    _execute_pogema_simulation(args, layout, tasks, schedule, paths)


def _execute_pogema_simulation(
    args,
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[tuple[int, int]]],
) -> None:
    try:
        from pogema import AnimationConfig, AnimationMonitor
        from pogema.envs import _make_pogema
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "POGEMA is required to run SVG simulation. Install pogema to execute "
            "warehouse_simulation.py."
        ) from exc

    logger = setup_logger("warehouse_agv")
    _log_tasks_and_schedule(logger, tasks, schedule, paths)
    logger.info("\n" + format_route_plan(layout.map, schedule, paths, args.operation_wait))

    grid_config = layout.to_grid_config(
        seed=args.seed, targets=build_pogema_targets(layout, schedule)
    )
    env = _make_pogema(grid_config)
    output_dir = build_output_directory(args)
    env = AnimationMonitor(
        env,
        animation_config=AnimationConfig(
            directory=output_dir,
            static=False,
            show_agents=True,
        ),
    )
    obs, info = env.reset()
    inner_env = env.unwrapped

    all_actions = [path_to_actions(path) for path in paths]
    agent_action_t = [0] * len(paths)
    executed_paths = [[path[0]] for path in paths]
    blocked_count = [0] * len(paths)
    total_reward = 0.0
    step = 0
    terminated = [False] * len(paths)

    for t in range(grid_config.max_episode_steps):
        actions = [
            all_actions[i][agent_action_t[i]]
            if agent_action_t[i] < len(all_actions[i])
            else 0
            for i in range(len(paths))
        ]
        positions_before = [tuple(pos) for pos in inner_env.grid.get_agents_xy()]
        obs, rewards, terminated, truncated, infos = env.step(actions)
        positions_after = [tuple(pos) for pos in inner_env.grid.get_agents_xy()]

        for i, action in enumerate(actions):
            if terminated[i]:
                continue
            if action != 0 and positions_after[i] == positions_before[i]:
                blocked_count[i] += 1
            else:
                agent_action_t[i] += 1

        for i, path in enumerate(paths):
            executed_paths[i].append(path[min(agent_action_t[i], len(path) - 1)])

        total_reward += sum(rewards)
        step += 1
        if all(agent_action_t[i] >= len(all_actions[i]) for i in range(len(paths))):
            terminated = [True] * len(paths)
            break
        if all(truncated):
            break

    animation_name, enhanced_output_path = build_pogema_output_names(
        args.planner, output_dir
    )
    out_path = save_animation(env, animation_name, output_dir)
    enhanced_path = save_enhanced_pogema_svg(
        out_path,
        layout,
        tasks,
        schedule,
        paths,
        enhanced_output_path,
        overlay_paths=executed_paths,
    )
    log_run_summary(
        logger,
        "warehouse_agv",
        step,
        total_reward,
        list(terminated),
        blocked_count,
        paths,
    )
    logger.info(f"Animation saved: {out_path}")
    logger.info(f"Enhanced animation saved: {enhanced_path}")
    env.close()


def _log_tasks_and_schedule(logger, tasks, schedule, paths) -> None:
    logger.info("Warehouse AGV simulation")
    for task in tasks:
        logger.info(
            f"Task {task.task_id}: {task.pickup_name}{task.pickup} -> "
            f"{task.dropoff_name}{task.dropoff}"
        )
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        task_ids = [task.task_id for task in agv_schedule.tasks]
        logger.info(
            f"AGV {agv_schedule.agv_id}: tasks={task_ids}, path_length={len(path)}"
        )
    if schedule.unassigned_tasks:
        logger.warning(
            "Unassigned tasks: "
            + ", ".join(task.task_id for task in schedule.unassigned_tasks)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Warehouse AGV scheduling simulation")
    parser.add_argument("--tasks", type=str, default=None, help="PICKUP:DROPOFF list")
    parser.add_argument("--random-tasks", type=int, default=None, help="Random task count")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agvs", type=int, default=4)
    parser.add_argument("--max-episode-steps", type=int, default=256)
    parser.add_argument(
        "--case-name",
        type=str,
        default="default",
        help="Output case folder under the animation root",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default="outputs/animations",
        help="Root folder for animation outputs",
    )
    parser.add_argument("--operation-wait", type=int, default=3)
    parser.add_argument("--turn-wait", type=int, default=2)
    parser.add_argument("--dispatch-gap", type=int, default=4)
    parser.add_argument(
        "--dispatch-policy",
        choices=["fixed", "asap"],
        default="fixed",
        help="fixed uses --dispatch-gap; asap removes artificial dispatch delay",
    )
    parser.add_argument(
        "--parking-policy",
        choices=["home", "nearest", "task-end"],
        default="home",
        help="Final parking target policy after assigned tasks finish",
    )
    parser.add_argument(
        "--buffer-points",
        type=str,
        default=None,
        help='Custom staging buffer cells as "row,col;row,col". Defaults to leftmost free cells.',
    )
    parser.add_argument(
        "--planner",
        choices=["prioritized", "cbs"],
        default="prioritized",
        help="Path conflict resolver to use",
    )
    parser.add_argument(
        "--scheduler",
        choices=["greedy", "ilp"],
        default="greedy",
        help="Task assignment strategy to use",
    )
    parser.add_argument(
        "--traffic-rules",
        choices=["none", "warehouse-zones"],
        default="none",
        help="Traffic rule profile used by path planning",
    )
    parser.add_argument("--list-locations", action="store_true")
    parser.add_argument(
        "--route-map",
        type=str,
        default=None,
        help="Annotated static SVG route map output path",
    )
    parser.add_argument(
        "--solution-animation",
        type=str,
        default=None,
        help="Annotated animated SVG solution output path",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run_warehouse_simulation(args)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
