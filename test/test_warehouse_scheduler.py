from warehouse.layouts import create_default_warehouse_layout
from warehouse.scheduler import schedule_tasks_greedy, schedule_tasks_ilp
from warehouse.tasks import TransportTask


def test_greedy_scheduler_assigns_task_to_nearest_agv():
    layout = create_default_warehouse_layout(num_agvs=2)
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=layout.pickup_points["S1"],
        dropoff_name="OUTBOUND",
        dropoff=layout.dropoff_points["OUTBOUND"],
    )

    result = schedule_tasks_greedy(layout.map, [(1, 1), (14, 14)], [task])

    assert result.unassigned_tasks == []
    assert result.agv_schedules[0].tasks == [task]
    assert result.agv_schedules[1].tasks == []


def test_scheduler_assigns_initial_tasks_to_idle_agvs_before_reusing_one_agv():
    layout = create_default_warehouse_layout(num_agvs=3)
    tasks = [
        TransportTask(
            task_id="T001",
            pickup_name="S1",
            pickup=layout.pickup_points["S1"],
            dropoff_name="OUTBOUND",
            dropoff=layout.dropoff_points["OUTBOUND"],
        ),
        TransportTask(
            task_id="T002",
            pickup_name="S3",
            pickup=layout.pickup_points["S3"],
            dropoff_name="PACKING",
            dropoff=layout.dropoff_points["PACKING"],
        ),
        TransportTask(
            task_id="T003",
            pickup_name="S12",
            pickup=layout.pickup_points["S12"],
            dropoff_name="INBOUND",
            dropoff=layout.dropoff_points["INBOUND"],
        ),
    ]

    result = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)

    assigned_counts = [len(schedule.tasks) for schedule in result.agv_schedules]
    assert assigned_counts == [1, 1, 1]


def test_scheduler_available_time_includes_operation_and_turn_waits():
    layout = create_default_warehouse_layout(num_agvs=1)
    task = TransportTask(
        task_id="T001",
        pickup_name="S11",
        pickup=layout.pickup_points["S11"],
        dropoff_name="PACKING",
        dropoff=layout.dropoff_points["PACKING"],
    )

    without_turn_wait = schedule_tasks_greedy(
        layout.map, layout.agv_starts, [task], operation_wait=3, turn_wait=0
    )
    with_turn_wait = schedule_tasks_greedy(
        layout.map, layout.agv_starts, [task], operation_wait=3, turn_wait=2
    )

    assert with_turn_wait.agv_schedules[0].available_at > without_turn_wait.agv_schedules[0].available_at


def test_greedy_scheduler_records_unreachable_tasks():
    blocked_map = [
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0],
    ]
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=(0, 2),
        dropoff_name="OUTBOUND",
        dropoff=(2, 2),
    )

    result = schedule_tasks_greedy(blocked_map, [(0, 0)], [task])

    assert result.agv_schedules[0].tasks == []
    assert result.unassigned_tasks == [task]


def test_ilp_scheduler_balances_workload_better_than_greedy_on_complex_case():
    layout = create_default_warehouse_layout(num_agvs=8)
    from warehouse.tasks import generate_random_tasks

    tasks = generate_random_tasks(layout, count=16, seed=23)

    greedy = schedule_tasks_greedy(
        layout.map, layout.agv_starts, tasks, operation_wait=3, turn_wait=2
    )
    ilp = schedule_tasks_ilp(
        layout.map, layout.agv_starts, tasks, operation_wait=3, turn_wait=2
    )

    assert ilp.unassigned_tasks == []
    assert max(schedule.available_at for schedule in ilp.agv_schedules) <= max(
        schedule.available_at for schedule in greedy.agv_schedules
    )
    assert all(schedule.tasks for schedule in ilp.agv_schedules)


def test_ilp_scheduler_records_unreachable_tasks():
    blocked_map = [
        [0, 1, 0],
        [1, 1, 1],
        [0, 1, 0],
    ]
    task = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=(0, 2),
        dropoff_name="OUTBOUND",
        dropoff=(2, 2),
    )

    result = schedule_tasks_ilp(blocked_map, [(0, 0)], [task])

    assert result.agv_schedules[0].tasks == []
    assert result.unassigned_tasks == [task]


def test_ilp_scheduler_optimizes_task_order_within_agv_route():
    grid_map = [[0 for _ in range(8)] for _ in range(8)]
    first_nearest_but_worse = TransportTask(
        task_id="T001",
        pickup_name="S1",
        pickup=(0, 1),
        dropoff_name="OUTBOUND",
        dropoff=(0, 2),
    )
    second_farther_but_better_first = TransportTask(
        task_id="T002",
        pickup_name="S2",
        pickup=(1, 0),
        dropoff_name="OUTBOUND",
        dropoff=(1, 1),
    )

    result = schedule_tasks_ilp(
        grid_map,
        [(0, 0)],
        [first_nearest_but_worse, second_farther_but_better_first],
        operation_wait=0,
        turn_wait=0,
    )

    assert [task.task_id for task in result.agv_schedules[0].tasks] == ["T002", "T001"]
