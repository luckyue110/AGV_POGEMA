import heapq

from warehouse.layouts import Coordinate
from warehouse.scheduler import AGVSchedule

ReservationTable = dict[tuple[int, int, int], int]
VertexConstraint = tuple[str, int, Coordinate]
EdgeConstraint = tuple[str, int, Coordinate, Coordinate]
Constraint = VertexConstraint | EdgeConstraint
ConstraintTable = dict[int, set[Constraint]]


def plan_scheduled_paths(
    grid_map: list[list[int]],
    schedules: list[AGVSchedule],
    operation_wait: int = 3,
    turn_wait: int = 2,
    parking_goals: list[Coordinate] | None = None,
    fallback_parking_goals: list[Coordinate] | None = None,
    dispatch_gap: int = 0,
) -> list[list[Coordinate]]:
    reservations: ReservationTable = {}
    _reserve_initial_dispatch_waits(reservations, schedules, dispatch_gap)
    paths = []

    for schedule in schedules:
        parking_goal = parking_goals[schedule.agv_id] if parking_goals else None
        full_path = _plan_single_agv_path(
            grid_map,
            schedule,
            operation_wait,
            turn_wait,
            parking_goal,
            fallback_parking_goals or [],
            dispatch_gap,
            reservations,
            constraints={},
        )
        if not full_path:
            full_path = _plan_single_agv_path(
                grid_map,
                schedule,
                operation_wait,
                turn_wait,
                parking_goal,
                fallback_parking_goals or [],
                dispatch_gap,
                reservations={},
                constraints={},
            )

        _reserve_path(
            reservations,
            full_path,
            schedule.agv_id,
            reserve_final=parking_goals is not None,
        )
        paths.append(full_path)

    return _resolve_path_collisions(
        paths,
        schedules,
        grid_map,
        operation_wait,
        turn_wait,
        parking_goals,
        fallback_parking_goals or [],
        dispatch_gap,
        hold_final=parking_goals is not None,
    )


def _plan_single_agv_path(
    grid_map: list[list[int]],
    schedule: AGVSchedule,
    operation_wait: int,
    turn_wait: int,
    parking_goal: Coordinate | None,
    fallback_parking_goals: list[Coordinate],
    dispatch_gap: int,
    reservations: ReservationTable,
    constraints: ConstraintTable,
) -> list[Coordinate]:
    current = schedule.start
    full_path = [current]
    _append_wait(full_path, current, schedule.agv_id * dispatch_gap)

    for task in schedule.tasks:
        to_pickup = astar_with_reservations(
            grid_map,
            current,
            task.pickup,
            reservations,
            len(full_path) - 1,
            agv_id=schedule.agv_id,
            constraints=constraints,
        )
        if to_pickup is None:
            return []
        if not _extend_with_turn_waits(
            full_path,
            to_pickup,
            turn_wait,
            reservations,
            grid_map,
            schedule.agv_id,
            constraints,
        ):
            return []
        if not _append_wait(
            full_path,
            task.pickup,
            operation_wait,
            reservations,
            grid_map,
            schedule.agv_id,
            constraints,
        ):
            return []
        current = task.pickup

        to_dropoff = astar_with_reservations(
            grid_map,
            current,
            task.dropoff,
            reservations,
            len(full_path) - 1,
            agv_id=schedule.agv_id,
            constraints=constraints,
        )
        if to_dropoff is None:
            return []
        if not _extend_with_turn_waits(
            full_path,
            to_dropoff,
            turn_wait,
            reservations,
            grid_map,
            schedule.agv_id,
            constraints,
        ):
            return []
        if not _append_wait(
            full_path,
            task.dropoff,
            operation_wait,
            reservations,
            grid_map,
            schedule.agv_id,
            constraints,
        ):
            return []
        current = task.dropoff

    if parking_goal is not None and schedule.tasks:
        to_parking = _find_parking_path(
            grid_map,
            current,
            parking_goal,
            fallback_parking_goals,
            reservations,
            len(full_path) - 1,
            schedule.agv_id,
            constraints,
        )
        if to_parking is None:
            return []
        if not _extend_with_turn_waits(
            full_path,
            to_parking,
            turn_wait,
            reservations,
            grid_map,
            schedule.agv_id,
            constraints,
        ):
            return []

    return full_path


def _resolve_path_collisions(
    paths: list[list[Coordinate]],
    schedules: list[AGVSchedule],
    grid_map: list[list[int]],
    operation_wait: int,
    turn_wait: int,
    parking_goals: list[Coordinate] | None,
    fallback_parking_goals: list[Coordinate],
    dispatch_gap: int,
    max_iterations: int = 1000,
    hold_final: bool = False,
) -> list[list[Coordinate]]:
    repaired = [list(path) for path in paths]
    constraints: ConstraintTable = {}

    for _ in range(max_iterations):
        collision = _first_path_collision(repaired, hold_final=hold_final)
        if collision is None:
            return repaired

        candidates = [max(collision[2], collision[3]), min(collision[2], collision[3])]
        for delayed_agv in candidates:
            constraint = _constraint_from_collision(collision, delayed_agv)
            trial_constraints = {
                agv_id: set(agent_constraints)
                for agv_id, agent_constraints in constraints.items()
            }
            trial_constraints.setdefault(delayed_agv, set()).add(constraint)

            reservations = _build_reservations_from_paths(
                [
                    path if agv_id != delayed_agv else []
                    for agv_id, path in enumerate(repaired)
                ],
                hold_final=hold_final,
            )
            parking_goal = parking_goals[delayed_agv] if parking_goals else None
            replanned = _plan_single_agv_path(
                grid_map,
                schedules[delayed_agv],
                operation_wait,
                turn_wait,
                parking_goal,
                fallback_parking_goals,
                dispatch_gap,
                reservations,
                trial_constraints,
            )
            if replanned:
                constraints = trial_constraints
                repaired[delayed_agv] = replanned
                break
        else:
            delayed_agv = candidates[0]
            if collision[0] == "vertex":
                _insert_wait_before_arrival(repaired[delayed_agv], collision[1], collision[4])
            else:
                _insert_wait_before(repaired[delayed_agv], collision[1])
    return repaired


def _constraint_from_collision(collision, delayed_agv: int) -> Constraint:
    kind = collision[0]
    time = collision[1]
    if kind == "vertex":
        position = collision[4]
        return ("vertex", time, position)

    _, swap_time, first_agv, second_agv, first_from, first_to = collision
    if delayed_agv == first_agv:
        return ("edge", swap_time, first_from, first_to)
    return ("edge", swap_time, first_to, first_from)


def _build_reservations_from_paths(
    paths: list[list[Coordinate]],
    hold_final: bool,
) -> ReservationTable:
    reservations: ReservationTable = {}
    for agv_id, path in enumerate(paths):
        if not path:
            continue
        _reserve_path(reservations, path, agv_id, reserve_final=hold_final)
    return reservations


def _first_path_collision(paths: list[list[Coordinate]], hold_final: bool = False):
    max_time = max((len(path) for path in paths), default=0)
    for time in range(max_time):
        occupied = {}
        for agv_id, path in enumerate(paths):
            position = _path_position_at(path, time, hold_final)
            if position is None:
                continue
            if position in occupied:
                return ("vertex", time, occupied[position], agv_id, position)
            occupied[position] = agv_id

    for time in range(max_time - 1):
        for agv_id, path in enumerate(paths):
            current = _path_position_at(path, time, hold_final)
            next_pos = _path_position_at(path, time + 1, hold_final)
            if current is None or next_pos is None:
                continue
            for other_id in range(agv_id + 1, len(paths)):
                other_current = _path_position_at(paths[other_id], time, hold_final)
                other_next = _path_position_at(paths[other_id], time + 1, hold_final)
                if other_current is None or other_next is None:
                    continue
                if current == other_next and next_pos == other_current:
                    return ("swap", time, agv_id, other_id, current, next_pos)
    return None


def _path_position_at(
    path: list[Coordinate], time: int, hold_final: bool = False
) -> Coordinate | None:
    if not hold_final and time >= len(path):
        return None
    return path[min(time, len(path) - 1)]


def _insert_wait_before(path: list[Coordinate], time: int) -> None:
    index = max(0, min(time, len(path) - 1))
    wait_position = path[index - 1] if index > 0 else path[0]
    path.insert(index, wait_position)


def _insert_wait_before_arrival(
    path: list[Coordinate], time: int, position: Coordinate
) -> None:
    index = max(0, min(time, len(path) - 1))
    while index > 0 and path[index - 1] == position:
        index -= 1
    wait_position = path[index - 1] if index > 0 else path[0]
    path.insert(index, wait_position)


def _reserve_initial_dispatch_waits(
    reservations: ReservationTable,
    schedules: list[AGVSchedule],
    dispatch_gap: int,
) -> None:
    if dispatch_gap <= 0:
        return
    for schedule in schedules:
        for time in range(schedule.agv_id * dispatch_gap + 1):
            row, col = schedule.start
            reservations[(row, col, time)] = schedule.agv_id


def _reserve_owned_parking_goals(
    reservations: ReservationTable,
    parking_goals: list[Coordinate],
    grid_map: list[list[int]],
) -> None:
    horizon = len(grid_map) * len(grid_map[0]) * 20
    for agv_id, (row, col) in enumerate(parking_goals):
        for time in range(horizon):
            reservations.setdefault((row, col, time), agv_id)


def _find_parking_path(
    grid_map: list[list[int]],
    current: Coordinate,
    preferred_goal: Coordinate,
    fallback_goals: list[Coordinate],
    reservations: ReservationTable,
    start_time: int,
    agv_id: int,
    constraints: ConstraintTable | None = None,
) -> list[Coordinate] | None:
    for goal in [preferred_goal] + fallback_goals:
        path = astar_with_reservations(
            grid_map,
            current,
            goal,
            reservations,
            start_time,
            agv_id=agv_id,
            constraints=constraints,
        )
        if path is not None:
            return path
    return None


def apply_turn_waits(path: list[Coordinate], turn_wait: int = 2) -> list[Coordinate]:
    if len(path) < 3 or turn_wait <= 0:
        return list(path)

    timed_path = [path[0], path[1]]
    previous_direction = _direction(path[0], path[1])
    for index in range(2, len(path)):
        current = path[index - 1]
        next_pos = path[index]
        next_direction = _direction(current, next_pos)
        if (
            previous_direction != (0, 0)
            and next_direction != (0, 0)
            and next_direction != previous_direction
        ):
            timed_path.extend([current] * turn_wait)
        timed_path.append(next_pos)
        previous_direction = next_direction
    return timed_path


def _extend_with_turn_waits(
    full_path: list[Coordinate],
    segment: list[Coordinate],
    turn_wait: int,
    reservations: ReservationTable | None = None,
    grid_map: list[list[int]] | None = None,
    agv_id: int | None = None,
    constraints: ConstraintTable | None = None,
) -> bool:
    timed_segment = apply_turn_waits(segment, turn_wait=turn_wait)
    if reservations is None or grid_map is None:
        full_path.extend(timed_segment[1:])
        return True

    max_delay = len(grid_map) * len(grid_map[0]) * 4
    for delay in range(max_delay + 1):
        candidate_extension = [segment[0]] * delay + timed_segment[1:]
        if not _extension_has_conflict(
            full_path, candidate_extension, reservations, agv_id, constraints
        ):
            full_path.extend(candidate_extension)
            return True

    return False


def _extension_has_conflict(
    full_path: list[Coordinate],
    extension: list[Coordinate],
    reservations: ReservationTable,
    agv_id: int | None = None,
    constraints: ConstraintTable | None = None,
) -> bool:
    if not extension:
        return False

    previous = full_path[-1]
    start_time = len(full_path) - 1
    for offset, position in enumerate(extension, start=1):
        time = start_time + offset
        if _is_reserved_by_other(reservations, position, time, agv_id):
            return True
        if _has_swap_conflict(reservations, previous, position, time - 1, agv_id):
            return True
        if _violates_constraint(
            constraints, agv_id, previous, position, time - 1
        ):
            return True
        previous = position
    return False


def _reserved_positions_at(
    reservations: ReservationTable, time: int, agv_id: int | None = None
) -> set[Coordinate]:
    return {
        (row, col)
        for (row, col, reserved_time), owner in reservations.items()
        if reserved_time == time and owner != agv_id
    }


def _append_wait(
    path: list[Coordinate],
    position: Coordinate,
    wait_steps: int,
    reservations: ReservationTable | None = None,
    grid_map: list[list[int]] | None = None,
    agv_id: int | None = None,
    constraints: ConstraintTable | None = None,
) -> bool:
    if wait_steps <= 0:
        return True
    extension = [position] * wait_steps
    if reservations is None or grid_map is None:
        path.extend(extension)
        return True

    max_delay = len(grid_map) * len(grid_map[0]) * 4
    for delay in range(max_delay + 1):
        candidate_extension = [path[-1]] * delay + extension
        if not _extension_has_conflict(
            path, candidate_extension, reservations, agv_id, constraints
        ):
            path.extend(candidate_extension)
            return True

    return False


def astar_with_reservations(
    grid_map: list[list[int]],
    start: Coordinate,
    goal: Coordinate,
    reservations: ReservationTable | None = None,
    start_time: int = 0,
    agv_id: int | None = None,
    constraints: ConstraintTable | None = None,
) -> list[Coordinate] | None:
    reservations = reservations or {}
    rows, cols = len(grid_map), len(grid_map[0])
    moves = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]
    max_t = rows * cols * 4

    if not _is_free(grid_map, start) or not _is_free(grid_map, goal):
        return None

    open_set = [(_heuristic(start, goal), 0, start_time, start[0], start[1])]
    came_from = {}
    visited = set()

    while open_set:
        _, cost, time, row, col = heapq.heappop(open_set)
        state = (row, col, time)
        if state in visited:
            continue
        visited.add(state)

        if (row, col) == goal:
            return _reconstruct_path(came_from, state)

        if time - start_time >= max_t:
            continue

        for dr, dc in moves:
            nr, nc, nt = row + dr, col + dc, time + 1
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if grid_map[nr][nc] == 1:
                continue
            if _is_reserved_by_other(reservations, (nr, nc), time, agv_id):
                continue
            if _is_reserved_by_other(reservations, (nr, nc), nt, agv_id):
                continue
            if _is_reserved_by_other(reservations, (nr, nc), nt + 1, agv_id):
                continue
            if _has_swap_conflict(
                reservations, (row, col), (nr, nc), time, agv_id
            ):
                continue
            if _violates_constraint(
                constraints, agv_id, (row, col), (nr, nc), time
            ):
                continue

            next_state = (nr, nc, nt)
            if next_state in visited:
                continue
            next_cost = cost + 1
            priority = next_cost + _heuristic((nr, nc), goal)
            heapq.heappush(open_set, (priority, next_cost, nt, nr, nc))
            if next_state not in came_from:
                came_from[next_state] = state

    return None


def path_to_actions(path: list[Coordinate]) -> list[int]:
    move_to_action = {
        (0, 0): 0,
        (-1, 0): 1,
        (1, 0): 2,
        (0, -1): 3,
        (0, 1): 4,
    }
    actions = []
    for index in range(len(path) - 1):
        dr = path[index + 1][0] - path[index][0]
        dc = path[index + 1][1] - path[index][1]
        actions.append(move_to_action.get((dr, dc), 0))
    return actions


def _reserve_path(
    reservations: ReservationTable,
    path: list[Coordinate],
    agv_id: int,
    reserve_final: bool = False,
) -> None:
    for time, (row, col) in enumerate(path):
        reservations[(row, col, time)] = agv_id
    if reserve_final:
        last_row, last_col = path[-1]
        for time in range(len(path), len(path) + 1000):
            reservations[(last_row, last_col, time)] = agv_id


def _has_swap_conflict(
    reservations: ReservationTable,
    current: Coordinate,
    next_pos: Coordinate,
    time: int,
    agv_id: int | None = None,
) -> bool:
    row, col = current
    nr, nc = next_pos
    return _is_reserved_by_other(
        reservations, (row, col), time + 1, agv_id
    ) and _is_reserved_by_other(reservations, (nr, nc), time, agv_id)


def _is_reserved_by_other(
    reservations: ReservationTable,
    position: Coordinate,
    time: int,
    agv_id: int | None = None,
) -> bool:
    owner = reservations.get((position[0], position[1], time))
    return owner is not None and owner != agv_id


def _violates_constraint(
    constraints: ConstraintTable | None,
    agv_id: int | None,
    current: Coordinate,
    next_pos: Coordinate,
    time: int,
) -> bool:
    if constraints is None or agv_id is None:
        return False
    agent_constraints = constraints.get(agv_id, set())
    return (
        ("vertex", time + 1, next_pos) in agent_constraints
        or ("edge", time, current, next_pos) in agent_constraints
    )


def _reconstruct_path(came_from: dict, state: tuple[int, int, int]) -> list[Coordinate]:
    path = [(state[0], state[1])]
    while state in came_from:
        state = came_from[state]
        path.append((state[0], state[1]))
    path.reverse()
    return path


def _heuristic(pos: Coordinate, goal: Coordinate) -> int:
    return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])


def _direction(start: Coordinate, end: Coordinate) -> Coordinate:
    return end[0] - start[0], end[1] - start[1]


def _is_free(grid_map: list[list[int]], pos: Coordinate) -> bool:
    row, col = pos
    return 0 <= row < len(grid_map) and 0 <= col < len(grid_map[0]) and grid_map[row][col] == 0
