import random
from dataclasses import dataclass

from warehouse.layouts import Coordinate, WarehouseLayout


@dataclass(frozen=True)
class TransportTask:
    task_id: str
    pickup_name: str
    pickup: Coordinate
    dropoff_name: str
    dropoff: Coordinate


def parse_task_spec(spec: str, layout: WarehouseLayout) -> list[TransportTask]:
    tasks = []
    entries = [entry.strip() for entry in spec.split(",") if entry.strip()]

    for index, entry in enumerate(entries, start=1):
        if ":" not in entry:
            raise ValueError(f"Task '{entry}' must use PICKUP:DROPOFF format")
        pickup_name, dropoff_name = [part.strip().upper() for part in entry.split(":", 1)]

        if pickup_name not in layout.pickup_points:
            raise ValueError(f"Unknown pickup '{pickup_name}'")
        if dropoff_name not in layout.dropoff_points:
            raise ValueError(f"Unknown dropoff '{dropoff_name}'")

        tasks.append(
            TransportTask(
                task_id=f"T{index:03d}",
                pickup_name=pickup_name,
                pickup=layout.pickup_points[pickup_name],
                dropoff_name=dropoff_name,
                dropoff=layout.dropoff_points[dropoff_name],
            )
        )

    return tasks


def generate_random_tasks(
    layout: WarehouseLayout, count: int, seed: int | None = None
) -> list[TransportTask]:
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = random.Random(seed)
    pickup_names = sorted(layout.pickup_points)
    dropoff_names = sorted(layout.dropoff_points)
    tasks = []

    for index in range(1, count + 1):
        pickup_name = rng.choice(pickup_names)
        dropoff_name = rng.choice(dropoff_names)
        tasks.append(
            TransportTask(
                task_id=f"T{index:03d}",
                pickup_name=pickup_name,
                pickup=layout.pickup_points[pickup_name],
                dropoff_name=dropoff_name,
                dropoff=layout.dropoff_points[dropoff_name],
            )
        )

    return tasks
