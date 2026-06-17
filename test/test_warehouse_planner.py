from warehouse.layouts import create_default_warehouse_layout
from warehouse.planner import (
    _plan_single_agv_path,
    apply_turn_waits,
    astar_with_reservations,
    path_to_actions,
    plan_scheduled_paths_cbs,
    plan_scheduled_paths,
)
from warehouse.scheduler import schedule_tasks_greedy
from warehouse.tasks import TransportTask, generate_random_tasks


def test_planner_builds_path_through_pickup_and_dropoff():
    layout = create_default_warehouse_layout(num_agvs=2)
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=layout.pickup_points["S1"],
        dropoff_name="OUTBOUND",
        dropoff=layout.dropoff_points["OUTBOUND"],
    )
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, [task])

    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    assigned_agv_id = next(
        schedule.agv_id for schedule in schedule.agv_schedules if schedule.tasks
    )
    assigned_path = paths[assigned_agv_id]
    assert assigned_path[0] == layout.agv_starts[assigned_agv_id]
    assert task.pickup in assigned_path
    assert task.dropoff in assigned_path
    assert assigned_path[-1] == task.dropoff
    assert len(path_to_actions(assigned_path)) == len(assigned_path) - 1


def test_planner_adds_pickup_and_dropoff_wait_time():
    layout = create_default_warehouse_layout(num_agvs=1)
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=layout.pickup_points["S1"],
        dropoff_name="OUTBOUND",
        dropoff=layout.dropoff_points["OUTBOUND"],
    )
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, [task])

    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules, operation_wait=3)

    path = paths[0]
    assert path.count(task.pickup) == 4
    assert path.count(task.dropoff) == 4


def test_planner_does_not_reserve_shared_station_for_100_steps():
    layout = create_default_warehouse_layout(num_agvs=2)
    tasks = [
        TransportTask(
            task_id="T001",
            pickup_name="S11",
            pickup=layout.pickup_points["S11"],
            dropoff_name="PACKING",
            dropoff=layout.dropoff_points["PACKING"],
        ),
        TransportTask(
            task_id="T002",
            pickup_name="S3",
            pickup=layout.pickup_points["S3"],
            dropoff_name="PACKING",
            dropoff=layout.dropoff_points["PACKING"],
        ),
    ]
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)

    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules, operation_wait=3)

    assert max(len(path) for path in paths) < 80


def test_apply_turn_waits_adds_two_steps_before_direction_change():
    timed_path = apply_turn_waits([(0, 0), (0, 1), (1, 1)], turn_wait=2)

    assert timed_path == [(0, 0), (0, 1), (0, 1), (0, 1), (1, 1)]


def test_apply_turn_waits_does_not_delay_straight_motion():
    timed_path = apply_turn_waits([(0, 0), (0, 1), (0, 2)], turn_wait=2)

    assert timed_path == [(0, 0), (0, 1), (0, 2)]


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


def test_planner_can_return_agv_to_parking_after_tasks():
    layout = create_default_warehouse_layout(num_agvs=1)
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=layout.pickup_points["S1"],
        dropoff_name="OUTBOUND",
        dropoff=layout.dropoff_points["OUTBOUND"],
    )
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, [task])

    paths = plan_scheduled_paths(
        layout.map,
        schedule.agv_schedules,
        operation_wait=3,
        turn_wait=2,
        parking_goals=layout.agv_starts,
    )

    assert task.dropoff in paths[0]
    assert paths[0][-1] == layout.agv_starts[0]


def test_planner_uses_fallback_parking_when_home_is_unreachable():
    grid_map = [
        [0, 1, 0],
        [0, 1, 1],
        [0, 0, 0],
    ]
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=(2, 0),
        dropoff_name="OUTBOUND",
        dropoff=(2, 2),
    )
    schedule = schedule_tasks_greedy(grid_map, [(0, 0)], [task])

    paths = plan_scheduled_paths(
        grid_map,
        schedule.agv_schedules,
        operation_wait=0,
        turn_wait=0,
        parking_goals=[(0, 2)],
        fallback_parking_goals=[(2, 1)],
    )

    assert paths[0][-1] == (2, 1)


def test_single_agv_replan_path_preserves_task_order_and_parking():
    layout = create_default_warehouse_layout(num_agvs=1)
    tasks = generate_random_tasks(layout, count=2, seed=7)
    schedule = schedule_tasks_greedy(
        layout.map, layout.agv_starts, tasks
    ).agv_schedules[0]

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


def test_planner_avoids_later_agv_start_during_dispatch_wait():
    layout = create_default_warehouse_layout(num_agvs=2)
    tasks = [
        TransportTask(
            task_id="T001",
            pickup_name="S23",
            pickup=layout.pickup_points["S23"],
            dropoff_name="OUTBOUND",
            dropoff=layout.dropoff_points["OUTBOUND"],
        )
    ]
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)

    paths = plan_scheduled_paths(
        layout.map,
        schedule.agv_schedules,
        operation_wait=0,
        turn_wait=0,
        dispatch_gap=12,
    )

    assigned_agv_id = next(
        agv_schedule.agv_id
        for agv_schedule in schedule.agv_schedules
        if agv_schedule.tasks
    )
    other_start = layout.agv_starts[1]
    assert assigned_agv_id == 0
    assert other_start not in paths[assigned_agv_id][:13]


def test_planner_turn_waits_do_not_create_vertex_or_swap_collisions():
    layout = create_default_warehouse_layout(num_agvs=8, max_episode_steps=2000)
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


def test_cbs_planner_solves_complex_case_without_vertex_or_swap_collisions():
    layout = create_default_warehouse_layout(num_agvs=8, max_episode_steps=3000)
    tasks = generate_random_tasks(layout, count=16, seed=23)
    schedule = schedule_tasks_greedy(
        layout.map,
        layout.agv_starts,
        tasks,
        operation_wait=3,
        turn_wait=2,
    )

    paths = plan_scheduled_paths_cbs(
        layout.map,
        schedule.agv_schedules,
        operation_wait=3,
        turn_wait=2,
        parking_goals=layout.agv_starts,
        fallback_parking_goals=layout.parking_points,
        dispatch_gap=12,
    )

    assert _first_collision(paths) is None
    assert max(len(path) for path in paths) <= 300
    assert sum(len(path) - 1 for path in paths) <= 1300


def _first_collision(paths):
    max_time = max(len(path) for path in paths)
    for time in range(max_time):
        occupied = {}
        for agv_id, path in enumerate(paths):
            position = _path_position_at(path, time)
            if position in occupied:
                return ("vertex", time, occupied[position], agv_id, position)
            occupied[position] = agv_id

    for time in range(max_time - 1):
        for agv_id, path in enumerate(paths):
            current = _path_position_at(path, time)
            next_pos = _path_position_at(path, time + 1)
            for other_id in range(agv_id + 1, len(paths)):
                other_current = _path_position_at(paths[other_id], time)
                other_next = _path_position_at(paths[other_id], time + 1)
                if current == other_next and next_pos == other_current:
                    return ("swap", time, agv_id, other_id, current, next_pos)
    return None


def _path_position_at(path, time):
    return path[min(time, len(path) - 1)]


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
