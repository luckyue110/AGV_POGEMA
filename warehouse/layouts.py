from dataclasses import dataclass

Coordinate = tuple[int, int]


@dataclass(frozen=True)
class WarehouseLayout:
    name: str
    map: list[list[int]]
    agv_starts: list[Coordinate]
    parking_points: list[Coordinate]
    buffer_points: list[Coordinate]
    shelf_points: dict[str, Coordinate]
    pickup_points: dict[str, Coordinate]
    dropoff_points: dict[str, Coordinate]
    station_points: dict[str, Coordinate]
    max_episode_steps: int = 256

    @property
    def size(self) -> int:
        return len(self.map)

    @property
    def all_named_points(self) -> dict[str, Coordinate]:
        return {**self.pickup_points, **self.dropoff_points}

    def to_grid_config(self, seed: int = 42, targets: list[Coordinate] | None = None):
        try:
            from pogema import GridConfig
        except ModuleNotFoundError:
            GridConfig = _FallbackGridConfig

        targets = targets or self._default_targets()
        return GridConfig(
            num_agents=len(self.agv_starts),
            size=self.size,
            map=self.map,
            agents_xy=self.agv_starts,
            targets_xy=targets,
            max_episode_steps=self.max_episode_steps,
            seed=seed,
            obs_radius=5,
            on_target="nothing",
            collision_system="soft",
        )

    def _default_targets(self) -> list[Coordinate]:
        fallback = next(iter(self.dropoff_points.values()))
        return [fallback for _ in self.agv_starts]


@dataclass(frozen=True)
class _FallbackGridConfig:
    num_agents: int
    size: int
    map: list[list[int]]
    agents_xy: list[Coordinate]
    targets_xy: list[Coordinate]
    max_episode_steps: int
    seed: int
    obs_radius: int = 5
    on_target: str = "nothing"
    collision_system: str = "soft"


def create_default_warehouse_layout(
    num_agvs: int = 4, max_episode_steps: int = 256
) -> WarehouseLayout:
    if not 1 <= num_agvs <= 8:
        raise ValueError("num_agvs must be between 1 and 8")

    size = 16
    grid = [[0 for _ in range(size)] for _ in range(size)]

    shelf_blocks = [
        (2, 3, 5, 4),
        (2, 6, 5, 7),
        (2, 10, 5, 11),
        (2, 13, 5, 14),
        (8, 3, 11, 4),
        (8, 6, 11, 7),
        (8, 10, 11, 11),
        (8, 13, 11, 14),
    ]
    for r1, c1, r2, c2 in shelf_blocks:
        for row in range(r1, r2 + 1):
            for col in range(c1, c2 + 1):
                grid[row][col] = 1

    station_points = {
        "INBOUND": (15, 8),
        "PACKING": (15, 11),
        "OUTBOUND": (15, 14),
    }
    for row, col in station_points.values():
        grid[row][col] = 1

    agv_starts = [
        (14, 1),
        (14, 5),
        (14, 7),
        (14, 10),
        (13, 1),
        (13, 5),
        (13, 9),
        (13, 13),
    ]
    parking_points = list(agv_starts)
    buffer_points = _build_buffer_points(grid, agv_starts)
    shelf_points, pickup_points = _build_shelf_and_pickup_points()
    dropoff_points = {
        "INBOUND": (14, 8),
        "PACKING": (14, 11),
        "OUTBOUND": (14, 14),
    }

    return WarehouseLayout(
        name="default_warehouse",
        map=grid,
        agv_starts=agv_starts[:num_agvs],
        parking_points=parking_points[:num_agvs],
        buffer_points=buffer_points[:num_agvs],
        shelf_points=shelf_points,
        pickup_points=pickup_points,
        dropoff_points=dropoff_points,
        station_points=station_points,
        max_episode_steps=max_episode_steps,
    )


def _build_buffer_points(
    grid: list[list[int]], agv_starts: list[Coordinate]
) -> list[Coordinate]:
    points = []
    used = set()
    for start_row, _ in agv_starts:
        for col in (0, 1):
            candidate = (start_row, col)
            if candidate not in used and grid[candidate[0]][candidate[1]] == 0:
                points.append(candidate)
                used.add(candidate)
                break
    for row in range(len(grid) - 1, -1, -1):
        for col in (0, 1):
            candidate = (row, col)
            if candidate not in used and grid[row][col] == 0:
                points.append(candidate)
                used.add(candidate)
    return points


def _build_shelf_and_pickup_points() -> tuple[dict[str, Coordinate], dict[str, Coordinate]]:
    shelf_to_service = [
        ((2, 3), (1, 3)),
        ((2, 4), (1, 4)),
        ((2, 6), (1, 6)),
        ((2, 7), (1, 7)),
        ((2, 10), (1, 10)),
        ((2, 11), (1, 11)),
        ((2, 13), (1, 13)),
        ((2, 14), (1, 14)),
        ((5, 3), (6, 3)),
        ((5, 4), (6, 4)),
        ((5, 6), (6, 6)),
        ((5, 7), (6, 7)),
        ((5, 10), (6, 10)),
        ((5, 11), (6, 11)),
        ((5, 13), (6, 13)),
        ((5, 14), (6, 14)),
        ((8, 3), (7, 3)),
        ((8, 6), (7, 6)),
        ((8, 10), (7, 10)),
        ((8, 13), (7, 13)),
        ((11, 4), (12, 4)),
        ((11, 7), (12, 7)),
        ((11, 11), (12, 11)),
        ((11, 14), (12, 14)),
    ]
    shelf_points = {}
    pickup_points = {}
    for index, (shelf, service) in enumerate(shelf_to_service, start=1):
        name = f"S{index}"
        shelf_points[name] = shelf
        pickup_points[name] = service
    return shelf_points, pickup_points
