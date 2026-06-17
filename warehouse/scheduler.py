from collections import deque
from dataclasses import dataclass, field
from itertools import combinations, permutations
from math import ceil

from warehouse.layouts import Coordinate
from warehouse.tasks import TransportTask
from warehouse.traffic import TrafficRules


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


@dataclass(frozen=True)
class _RouteCandidate:
    agv_id: int
    task_indices: frozenset[int]
    ordered_indices: tuple[int, ...]
    cost: int


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


def schedule_tasks_ilp(
    grid_map: list[list[int]],
    agv_starts: list[Coordinate],
    tasks: list[TransportTask],
    operation_wait: int = 3,
    turn_wait: int = 2,
    parking_goals: list[Coordinate] | None = None,
    fallback_parking_goals: list[Coordinate] | None = None,
    dispatch_gap: int = 0,
    staging_goals: list[Coordinate] | None = None,
    optimize_route_sets: bool = False,
    traffic_rules: TrafficRules | None = None,
) -> ScheduleResult:
    schedules = [AGVSchedule(agv_id=i, start=start) for i, start in enumerate(agv_starts)]
    if not tasks:
        return ScheduleResult(agv_schedules=schedules, unassigned_tasks=[])

    route_result = (
        _schedule_tasks_by_route_set_partition(
            grid_map, agv_starts, tasks, operation_wait, turn_wait
        )
        if optimize_route_sets
        else None
    )
    cost_matrix, reachable_tasks, unassigned = _build_assignment_cost_matrix(
        grid_map, agv_starts, tasks, operation_wait, turn_wait
    )
    if not reachable_tasks:
        return ScheduleResult(agv_schedules=schedules, unassigned_tasks=unassigned)

    assignment = _solve_minimax_assignment(cost_matrix)
    assigned_by_agv: list[list[TransportTask]] = [[] for _ in agv_starts]
    for task_index, agv_id in enumerate(assignment):
        assigned_by_agv[agv_id].append(reachable_tasks[task_index])

    for schedule, assigned_tasks in zip(schedules, assigned_by_agv):
        ordered_tasks = _order_tasks_min_route_cost(
            grid_map, schedule.start, assigned_tasks, operation_wait, turn_wait
        )
        schedule.tasks.extend(ordered_tasks)
        schedule.estimated_position = schedule.start
        schedule.estimated_cost = 0
        schedule.available_at = 0
        for task in ordered_tasks:
            cost = _task_chain_cost(
                grid_map,
                schedule.estimated_position,
                task,
                operation_wait,
                turn_wait,
            )
            if cost is None:
                unassigned.append(task)
                continue
            schedule.estimated_position = task.dropoff
            schedule.estimated_cost += cost
            schedule.available_at += cost

    ilp_result = ScheduleResult(agv_schedules=schedules, unassigned_tasks=unassigned)
    if parking_goals is None:
        if route_result is not None and _estimated_schedule_score(route_result) < _estimated_schedule_score(ilp_result):
            return route_result
        return ilp_result

    greedy_result = schedule_tasks_greedy(
        grid_map,
        agv_starts,
        tasks,
        operation_wait=operation_wait,
        turn_wait=turn_wait,
    )
    return _choose_shorter_planned_schedule(
        grid_map,
        [candidate for candidate in [route_result, ilp_result, greedy_result] if candidate is not None],
        operation_wait,
        turn_wait,
        parking_goals,
        fallback_parking_goals or [],
        dispatch_gap,
        staging_goals,
        traffic_rules,
    )


def _schedule_tasks_by_route_set_partition(
    grid_map: list[list[int]],
    agv_starts: list[Coordinate],
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
) -> ScheduleResult | None:
    max_route_size = _max_route_candidate_size(len(tasks), len(agv_starts))
    if len(tasks) > max_route_size * len(agv_starts):
        return None

    candidates = _build_route_candidates(
        grid_map, agv_starts, tasks, operation_wait, turn_wait, max_route_size
    )
    selected = _solve_route_set_partition(candidates, len(tasks), len(agv_starts))
    if selected is None:
        return None

    schedules = [AGVSchedule(agv_id=i, start=start) for i, start in enumerate(agv_starts)]
    for candidate in selected:
        schedule = schedules[candidate.agv_id]
        ordered_tasks = [tasks[index] for index in candidate.ordered_indices]
        schedule.tasks.extend(ordered_tasks)
        schedule.estimated_position = schedule.start
        schedule.estimated_cost = 0
        schedule.available_at = 0
        for task in ordered_tasks:
            cost = _task_chain_cost(
                grid_map,
                schedule.estimated_position,
                task,
                operation_wait,
                turn_wait,
            )
            if cost is None:
                return None
            schedule.estimated_position = task.dropoff
            schedule.estimated_cost += cost
            schedule.available_at += cost
    return ScheduleResult(agv_schedules=schedules, unassigned_tasks=[])


def _max_route_candidate_size(task_count: int, agv_count: int) -> int:
    if agv_count == 0:
        return 0
    average = ceil(task_count / agv_count)
    return min(task_count, max(2, average))


def _build_route_candidates(
    grid_map: list[list[int]],
    agv_starts: list[Coordinate],
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
    max_route_size: int,
) -> list[_RouteCandidate]:
    candidates = []
    path_cost_cache: dict[tuple[Coordinate, Coordinate, int], int | None] = {}
    task_indices = range(len(tasks))
    for agv_id, start in enumerate(agv_starts):
        for route_size in range(1, max_route_size + 1):
            for subset in combinations(task_indices, route_size):
                best_order = None
                best_cost = None
                for ordered in permutations(subset):
                    ordered_tasks = [tasks[index] for index in ordered]
                    cost = _route_cost_with_cache(
                        grid_map,
                        start,
                        ordered_tasks,
                        operation_wait,
                        turn_wait,
                        return_home=True,
                        path_cost_cache=path_cost_cache,
                    )
                    if cost is not None and (best_cost is None or cost < best_cost):
                        best_cost = cost
                        best_order = ordered
                if best_order is not None and best_cost is not None:
                    candidates.append(
                        _RouteCandidate(
                            agv_id=agv_id,
                            task_indices=frozenset(subset),
                            ordered_indices=tuple(best_order),
                            cost=best_cost,
                        )
                    )
    return candidates


def _solve_route_set_partition(
    candidates: list[_RouteCandidate],
    task_count: int,
    agv_count: int,
) -> list[_RouteCandidate] | None:
    if task_count == 0:
        return []
    if task_count > 20:
        return None

    candidates_by_agv: list[list[_RouteCandidate]] = [[] for _ in range(agv_count)]
    for candidate in candidates:
        candidates_by_agv[candidate.agv_id].append(candidate)

    candidate_masks = {
        candidate: sum(1 << task_index for task_index in candidate.task_indices)
        for candidate in candidates
    }
    full_mask = (1 << task_count) - 1
    dp: dict[int, tuple[tuple[int, int], list[_RouteCandidate]]] = {0: ((0, 0), [])}

    for agv_id in range(agv_count):
        next_dp = dict(dp)
        for mask, (score, selected) in dp.items():
            for candidate in candidates_by_agv[agv_id]:
                candidate_mask = candidate_masks[candidate]
                if mask & candidate_mask:
                    continue
                next_mask = mask | candidate_mask
                next_score = (
                    max(score[0], candidate.cost),
                    score[1] + candidate.cost,
                )
                previous = next_dp.get(next_mask)
                if previous is None or next_score < previous[0]:
                    next_dp[next_mask] = (next_score, selected + [candidate])
        dp = next_dp

    solution = dp.get(full_mask)
    if solution is None:
        return None
    return solution[1]


def _estimated_schedule_score(result: ScheduleResult) -> tuple[int, int]:
    loads = [schedule.available_at for schedule in result.agv_schedules]
    return max(loads, default=0), sum(loads)


def _choose_shorter_planned_schedule(
    grid_map: list[list[int]],
    candidates: list[ScheduleResult],
    operation_wait: int,
    turn_wait: int,
    parking_goals: list[Coordinate],
    fallback_parking_goals: list[Coordinate],
    dispatch_gap: int,
    staging_goals: list[Coordinate] | None,
    traffic_rules: TrafficRules | None,
) -> ScheduleResult:
    from warehouse.planner import plan_scheduled_paths

    best_result = candidates[0]
    best_score = (10**18, 10**18)
    for result in candidates:
        paths = plan_scheduled_paths(
            grid_map,
            result.agv_schedules,
            operation_wait=operation_wait,
            turn_wait=turn_wait,
            parking_goals=parking_goals,
            fallback_parking_goals=fallback_parking_goals,
            dispatch_gap=dispatch_gap,
            staging_goals=staging_goals,
            traffic_rules=traffic_rules,
        )
        score = (
            max((len(path) for path in paths), default=0),
            sum(len(path) for path in paths),
        )
        if score < best_score:
            best_score = score
            best_result = result
    return best_result


def _build_assignment_cost_matrix(
    grid_map: list[list[int]],
    agv_starts: list[Coordinate],
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
) -> tuple[list[list[int]], list[TransportTask], list[TransportTask]]:
    cost_matrix = []
    reachable_tasks = []
    unassigned = []
    for task in tasks:
        task_costs = []
        for start in agv_starts:
            cost = _task_round_trip_cost(
                grid_map, start, task, operation_wait, turn_wait
            )
            task_costs.append(cost)
        if all(cost is None for cost in task_costs):
            unassigned.append(task)
            continue
        finite_costs = [cost if cost is not None else 10**9 for cost in task_costs]
        cost_matrix.append(finite_costs)
        reachable_tasks.append(task)
    return cost_matrix, reachable_tasks, unassigned


def _solve_minimax_assignment(cost_matrix: list[list[int]]) -> list[int]:
    scipy_assignment = _solve_minimax_assignment_with_scipy(cost_matrix)
    if scipy_assignment is not None:
        return scipy_assignment
    return _solve_minimax_assignment_branch_and_bound(cost_matrix)


def _solve_minimax_assignment_with_scipy(cost_matrix: list[list[int]]) -> list[int] | None:
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
    except ModuleNotFoundError:
        return None

    task_count = len(cost_matrix)
    agv_count = len(cost_matrix[0]) if task_count else 0
    variable_count = task_count * agv_count + 1
    makespan_index = variable_count - 1

    c = np.zeros(variable_count)
    c[makespan_index] = 1
    integrality = np.ones(variable_count)
    integrality[makespan_index] = 0

    constraints = []
    lower_bounds = []
    upper_bounds = []

    for task_index in range(task_count):
        row = np.zeros(variable_count)
        for agv_id in range(agv_count):
            row[task_index * agv_count + agv_id] = 1
        constraints.append(row)
        lower_bounds.append(1)
        upper_bounds.append(1)

    for agv_id in range(agv_count):
        row = np.zeros(variable_count)
        for task_index in range(task_count):
            row[task_index * agv_count + agv_id] = cost_matrix[task_index][agv_id]
        row[makespan_index] = -1
        constraints.append(row)
        lower_bounds.append(-np.inf)
        upper_bounds.append(0)

    result = milp(
        c,
        integrality=integrality,
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count) * np.inf),
        constraints=LinearConstraint(np.vstack(constraints), lower_bounds, upper_bounds),
        options={"time_limit": 30},
    )
    if not result.success:
        return None

    values = result.x[: task_count * agv_count].reshape((task_count, agv_count))
    return [int(np.argmax(values[task_index])) for task_index in range(task_count)]


def _solve_minimax_assignment_branch_and_bound(cost_matrix: list[list[int]]) -> list[int]:
    task_order = sorted(
        range(len(cost_matrix)),
        key=lambda task_index: min(cost_matrix[task_index]),
        reverse=True,
    )
    agv_count = len(cost_matrix[0])
    loads = [0] * agv_count
    current = [0] * len(cost_matrix)
    best = [0] * len(cost_matrix)
    best_makespan = 10**18
    best_total = 10**18

    def search(order_index: int) -> None:
        nonlocal best_makespan, best_total, best
        if order_index == len(task_order):
            makespan = max(loads, default=0)
            total = sum(loads)
            if (makespan, total) < (best_makespan, best_total):
                best_makespan = makespan
                best_total = total
                best = list(current)
            return

        task_index = task_order[order_index]
        for agv_id in sorted(range(agv_count), key=lambda item: loads[item]):
            cost = cost_matrix[task_index][agv_id]
            if cost >= 10**9:
                continue
            next_load = loads[agv_id] + cost
            if max(next_load, max(loads)) > best_makespan:
                continue
            loads[agv_id] = next_load
            current[task_index] = agv_id
            search(order_index + 1)
            loads[agv_id] -= cost

    search(0)
    return best


def _order_tasks_nearest_neighbor(
    grid_map: list[list[int]],
    start: Coordinate,
    tasks: list[TransportTask],
    turn_wait: int,
) -> list[TransportTask]:
    ordered = []
    remaining = list(tasks)
    current = start
    while remaining:
        best_task = min(
            remaining,
            key=lambda task: (
                _path_cost_between(grid_map, current, task.pickup, turn_wait) or 10**9,
                task.task_id,
            ),
        )
        ordered.append(best_task)
        remaining.remove(best_task)
        current = best_task.dropoff
    return ordered


def _order_tasks_min_route_cost(
    grid_map: list[list[int]],
    start: Coordinate,
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
) -> list[TransportTask]:
    if len(tasks) <= 1:
        return list(tasks)
    if len(tasks) > 7:
        return _order_tasks_nearest_neighbor(grid_map, start, tasks, turn_wait)

    best_order = None
    best_cost = None
    for ordered in permutations(tasks):
        cost = _route_cost(
            grid_map,
            start,
            list(ordered),
            operation_wait,
            turn_wait,
            return_home=False,
        )
        if cost is not None and (best_cost is None or cost < best_cost):
            best_order = list(ordered)
            best_cost = cost
    return best_order or _order_tasks_nearest_neighbor(grid_map, start, tasks, turn_wait)


def _route_cost(
    grid_map: list[list[int]],
    start: Coordinate,
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
    return_home: bool,
) -> int | None:
    current = start
    total = 0
    for task in tasks:
        cost = _task_chain_cost(grid_map, current, task, operation_wait, turn_wait)
        if cost is None:
            return None
        total += cost
        current = task.dropoff
    if return_home:
        home_cost = _path_cost_between(grid_map, current, start, turn_wait)
        if home_cost is None:
            return None
        total += home_cost
    return total


def _route_cost_with_cache(
    grid_map: list[list[int]],
    start: Coordinate,
    tasks: list[TransportTask],
    operation_wait: int,
    turn_wait: int,
    return_home: bool,
    path_cost_cache: dict[tuple[Coordinate, Coordinate, int], int | None],
) -> int | None:
    current = start
    total = 0
    for task in tasks:
        to_pickup = _cached_path_cost(
            grid_map, current, task.pickup, turn_wait, path_cost_cache
        )
        to_dropoff = _cached_path_cost(
            grid_map, task.pickup, task.dropoff, turn_wait, path_cost_cache
        )
        if to_pickup is None or to_dropoff is None:
            return None
        total += to_pickup + to_dropoff + operation_wait * 2
        current = task.dropoff
    if return_home:
        home_cost = _cached_path_cost(
            grid_map, current, start, turn_wait, path_cost_cache
        )
        if home_cost is None:
            return None
        total += home_cost
    return total


def _cached_path_cost(
    grid_map: list[list[int]],
    start: Coordinate,
    goal: Coordinate,
    turn_wait: int,
    cache: dict[tuple[Coordinate, Coordinate, int], int | None],
) -> int | None:
    key = (start, goal, turn_wait)
    if key not in cache:
        cache[key] = _path_cost_between(grid_map, start, goal, turn_wait)
    return cache[key]


def _task_round_trip_cost(
    grid_map: list[list[int]],
    start: Coordinate,
    task: TransportTask,
    operation_wait: int,
    turn_wait: int,
) -> int | None:
    to_pickup = _path_cost_between(grid_map, start, task.pickup, turn_wait)
    to_dropoff = _path_cost_between(grid_map, task.pickup, task.dropoff, turn_wait)
    to_home = _path_cost_between(grid_map, task.dropoff, start, turn_wait)
    if to_pickup is None or to_dropoff is None or to_home is None:
        return None
    return to_pickup + to_dropoff + to_home + operation_wait * 2


def _task_chain_cost(
    grid_map: list[list[int]],
    current: Coordinate,
    task: TransportTask,
    operation_wait: int,
    turn_wait: int,
) -> int | None:
    to_pickup = _path_cost_between(grid_map, current, task.pickup, turn_wait)
    to_dropoff = _path_cost_between(grid_map, task.pickup, task.dropoff, turn_wait)
    if to_pickup is None or to_dropoff is None:
        return None
    return to_pickup + to_dropoff + operation_wait * 2


def _path_cost_between(
    grid_map: list[list[int]], start: Coordinate, goal: Coordinate, turn_wait: int
) -> int | None:
    path = _bfs_path(grid_map, start, goal)
    if path is None:
        return None
    return _timed_path_cost(path, turn_wait)


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
