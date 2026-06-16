import pytest

from warehouse.layouts import create_default_warehouse_layout
from warehouse.tasks import generate_random_tasks, parse_task_spec


def test_parse_task_spec_builds_named_transport_tasks():
    layout = create_default_warehouse_layout()

    tasks = parse_task_spec("S1:OUTBOUND,S3:PACKING", layout)

    assert [task.task_id for task in tasks] == ["T001", "T002"]
    assert tasks[0].pickup_name == "S1"
    assert tasks[0].pickup == layout.pickup_points["S1"]
    assert tasks[0].dropoff_name == "OUTBOUND"
    assert tasks[0].dropoff == layout.dropoff_points["OUTBOUND"]
    assert tasks[1].pickup_name == "S3"
    assert tasks[1].dropoff_name == "PACKING"


def test_parse_task_spec_rejects_unknown_names():
    layout = create_default_warehouse_layout()

    with pytest.raises(ValueError, match="Unknown pickup"):
        parse_task_spec("BAD:OUTBOUND", layout)

    with pytest.raises(ValueError, match="Unknown dropoff"):
        parse_task_spec("S1:BAD", layout)


def test_generate_random_tasks_uses_valid_points():
    layout = create_default_warehouse_layout()

    tasks = generate_random_tasks(layout, count=10, seed=42)

    assert len(tasks) == 10
    for task in tasks:
        assert task.pickup_name in layout.pickup_points
        assert task.dropoff_name in layout.dropoff_points
        assert task.pickup == layout.pickup_points[task.pickup_name]
        assert task.dropoff == layout.dropoff_points[task.dropoff_name]
