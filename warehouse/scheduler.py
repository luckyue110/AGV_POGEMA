from collections import deque
from dataclasses import dataclass, field

from warehouse.layouts import Coordinate
from warehouse.tasks import TransportTask


@dataclass
class AGVSchedule:
    agv_id: int
    start: Coordinate
    tasks: list[TransportTask] = field(default_factory=list)
    estimated_position: Coordinate | None = None
    estimated_cost: int = 0
    available_at: int = 0

    def __post_init__(self):
        if self.estimated_position is None:
            self.estimated_position = self.start


@dataclass
class ScheduleResult:
    agv_schedules: list[AGVSchedule]
    unassigned_tasks: list[TransportTask]


def schedule_tasks_greedy(
    grid_map: list[list[int]],
    agv_starts: list[Coordinate],
    tasks: list[TransportTask],
    operation_wait: int = 3,
    turn_wait: int = 2,
) -> ScheduleResult:
    schedules = [AGVSchedule(agv_id=i, start=start) for i, start in enumerate(agv_starts)]
    remaining_tasks = list(tasks)
    unassigned = []

    while remaining_tasks:
        schedule = min(schedules, key=lambda item: (item.available_at, item.agv_id))
        best_task = None
        best_cost = None

        for task in remaining_tasks:
            to_pickup_path = _bfs_path(
                grid_map, schedule.estimated_position, task.pickup
            )
            pickup_to_dropoff_path = _bfs_path(grid_map, task.pickup, task.dropoff)
            if to_pickup_path is None or pickup_to_dropoff_path is None:
                continue

            cost = _timed_path_cost(to_pickup_path, turn_wait) + _timed_path_cost(
                pickup_to_dropoff_path, turn_wait
            )
            if best_cost is None or cost < best_cost:
                best_task = task
                best_cost = cost

        if best_task is None:
            unassigned.extend(remaining_tasks)
            break

        schedule.tasks.append(best_task)
        schedule.estimated_position = best_task.dropoff
        schedule.estimated_cost += best_cost
        schedule.available_at += best_cost + operation_wait * 2
        remaining_tasks.remove(best_task)

    return ScheduleResult(agv_schedules=schedules, unassigned_tasks=unassigned)


def shortest_path_length(
    grid_map: list[list[int]], start: Coordinate, goal: Coordinate
) -> int | None:
    path = _bfs_path(grid_map, start, goal)
    if path is None:
        return None
    return len(path) - 1


def _timed_path_cost(path: list[Coordinate], turn_wait: int) -> int:
    if not path:
        return 0
    cost = len(path) - 1
    previous_direction = None
    for index in range(1, len(path)):
        direction = (
            path[index][0] - path[index - 1][0],
            path[index][1] - path[index - 1][1],
        )
        if previous_direction is not None and direction != previous_direction:
            cost += turn_wait
        previous_direction = direction
    return cost


def _bfs_path(
    grid_map: list[list[int]], start: Coordinate, goal: Coordinate
) -> list[Coordinate] | None:
    rows, cols = len(grid_map), len(grid_map[0])
    if not _is_free(grid_map, start) or not _is_free(grid_map, goal):
        return None

    queue = deque([start])
    came_from = {start: None}
    moves = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while queue:
        current = queue.popleft()
        if current == goal:
            break

        row, col = current
        for dr, dc in moves:
            next_pos = (row + dr, col + dc)
            nr, nc = next_pos
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if not _is_free(grid_map, next_pos):
                continue
            if next_pos in came_from:
                continue
            came_from[next_pos] = current
            queue.append(next_pos)

    if goal not in came_from:
        return None

    path = []
    current = goal
    while current is not None:
        path.append(current)
        current = came_from[current]
    path.reverse()
    return path


def _is_free(grid_map: list[list[int]], pos: Coordinate) -> bool:
    row, col = pos
    return 0 <= row < len(grid_map) and 0 <= col < len(grid_map[0]) and grid_map[row][col] == 0
