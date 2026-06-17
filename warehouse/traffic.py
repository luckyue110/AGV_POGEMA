from dataclasses import dataclass, field

from warehouse.layouts import Coordinate, WarehouseLayout

Direction = tuple[int, int]

EAST: Direction = (0, 1)
WEST: Direction = (0, -1)
NORTH: Direction = (-1, 0)
SOUTH: Direction = (1, 0)
WAIT: Direction = (0, 0)


@dataclass(frozen=True)
class TrafficRules:
    horizontal_rows: dict[int, Direction] = field(default_factory=dict)
    vertical_cols: dict[int, Direction] = field(default_factory=dict)
    two_way_cells: frozenset[Coordinate] = frozenset()

    def allows_move(self, current: Coordinate, next_pos: Coordinate) -> bool:
        direction = (next_pos[0] - current[0], next_pos[1] - current[1])
        if direction == WAIT:
            return True
        if current in self.two_way_cells or next_pos in self.two_way_cells:
            return True
        if direction in (EAST, WEST):
            required = self.horizontal_rows.get(current[0])
            return required is None or direction == required
        if direction in (NORTH, SOUTH):
            required = self.vertical_cols.get(current[1])
            return required is None or direction == required
        return False


def build_warehouse_zone_traffic_rules(layout: WarehouseLayout) -> TrafficRules:
    two_way_cells = set(layout.buffer_points)
    two_way_cells.update(layout.agv_starts)
    two_way_cells.update(layout.parking_points)
    two_way_cells.update(layout.pickup_points.values())
    two_way_cells.update(layout.dropoff_points.values())

    for point in list(two_way_cells):
        two_way_cells.update(_free_neighbors(layout.map, point))

    return TrafficRules(
        horizontal_rows={
            7: EAST,
            12: WEST,
        },
        vertical_cols={},
        two_way_cells=frozenset(two_way_cells),
    )


def _free_neighbors(
    grid_map: list[list[int]], point: Coordinate
) -> list[Coordinate]:
    row, col = point
    neighbors = []
    for dr, dc in (NORTH, SOUTH, WEST, EAST):
        candidate = (row + dr, col + dc)
        if _is_free(grid_map, candidate):
            neighbors.append(candidate)
    return neighbors


def _is_free(grid_map: list[list[int]], point: Coordinate) -> bool:
    row, col = point
    return 0 <= row < len(grid_map) and 0 <= col < len(grid_map[0]) and grid_map[row][col] == 0
