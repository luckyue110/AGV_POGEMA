import argparse

from utils.result_saver import log_run_summary, save_animation, setup_logger
from warehouse.layouts import WarehouseLayout, create_default_warehouse_layout
from warehouse.planner import path_to_actions, plan_scheduled_paths
from warehouse.scheduler import ScheduleResult, schedule_tasks_greedy, shortest_path_length
from warehouse.tasks import TransportTask, generate_random_tasks, parse_task_spec
from warehouse.visualization import save_route_map_svg, save_solution_animation_svg
from warehouse.visualization import save_enhanced_pogema_svg


def build_tasks_from_args(args, layout: WarehouseLayout) -> list[TransportTask]:
    if args.tasks:
        return parse_task_spec(args.tasks, layout)

    count = args.random_tasks if args.random_tasks is not None else 4
    return generate_random_tasks(layout, count=count, seed=args.seed)


def format_locations(layout: WarehouseLayout) -> str:
    lines = ["Pickup points:"]
    for name, coord in sorted(layout.pickup_points.items()):
        lines.append(f"  {name}: {coord}")
    lines.append("Dropoff points:")
    for name, coord in sorted(layout.dropoff_points.items()):
        lines.append(f"  {name}: {coord}")
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


def run_warehouse_simulation(args) -> None:
    layout = create_default_warehouse_layout(
        num_agvs=args.agvs, max_episode_steps=args.max_episode_steps
    )

    if args.list_locations:
        print(format_locations(layout))
        return

    tasks = build_tasks_from_args(args, layout)
    schedule = schedule_tasks_greedy(
        layout.map,
        layout.agv_starts,
        tasks,
        operation_wait=args.operation_wait,
        turn_wait=args.turn_wait,
    )
    paths = plan_scheduled_paths(
        layout.map,
        schedule.agv_schedules,
        operation_wait=args.operation_wait,
        turn_wait=args.turn_wait,
        parking_goals=layout.agv_starts,
        fallback_parking_goals=layout.parking_points,
        dispatch_gap=args.dispatch_gap,
    )
    route_map_path = save_route_map_svg(layout, tasks, schedule, paths, args.route_map)
    animation_path = save_solution_animation_svg(
        layout, tasks, schedule, paths, args.solution_animation
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
    env = AnimationMonitor(
        env,
        animation_config=AnimationConfig(
            directory="outputs/animations",
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

    out_path = save_animation(env, "warehouse_agv")
    enhanced_path = save_enhanced_pogema_svg(
        out_path,
        layout,
        tasks,
        schedule,
        paths,
        "outputs/animations/warehouse_agv_enhanced.svg",
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
    parser.add_argument("--operation-wait", type=int, default=3)
    parser.add_argument("--turn-wait", type=int, default=2)
    parser.add_argument("--dispatch-gap", type=int, default=4)
    parser.add_argument("--list-locations", action="store_true")
    parser.add_argument(
        "--route-map",
        type=str,
        default="outputs/animations/warehouse_route_map.svg",
        help="Annotated static SVG route map output path",
    )
    parser.add_argument(
        "--solution-animation",
        type=str,
        default="outputs/animations/warehouse_solution_animated.svg",
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
