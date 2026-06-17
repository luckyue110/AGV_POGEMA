from warehouse.layouts import create_default_warehouse_layout


def test_default_layout_has_free_agv_starts_and_named_points():
    layout = create_default_warehouse_layout(num_agvs=4)

    assert len(layout.agv_starts) == 4
    assert len(layout.parking_points) == 4
    assert len(layout.buffer_points) == 4
    assert layout.pickup_points
    assert layout.shelf_points
    assert layout.dropoff_points
    assert layout.station_points

    for row, col in layout.agv_starts:
        assert layout.map[row][col] == 0
    for row, col in layout.parking_points:
        assert layout.map[row][col] == 0
    for row, col in layout.buffer_points:
        assert col in (0, 1)
        assert layout.map[row][col] == 0
    for row, col in layout.shelf_points.values():
        assert layout.map[row][col] == 1
    for row, col in layout.station_points.values():
        assert layout.map[row][col] == 1

    for points in (layout.pickup_points, layout.dropoff_points):
        for name, (row, col) in points.items():
            assert name
            assert layout.map[row][col] == 0


def test_pickup_service_points_are_adjacent_to_blocked_shelf_cells():
    layout = create_default_warehouse_layout(num_agvs=8)

    assert len(layout.agv_starts) == 8
    assert len(layout.pickup_points) >= 20
    for name, shelf in layout.shelf_points.items():
        service = layout.pickup_points[name]
        distance = abs(shelf[0] - service[0]) + abs(shelf[1] - service[1])
        assert distance == 1


def test_dropoff_service_points_are_adjacent_to_blocked_station_cells():
    layout = create_default_warehouse_layout(num_agvs=4)

    for name, station in layout.station_points.items():
        service = layout.dropoff_points[name]
        distance = abs(station[0] - service[0]) + abs(station[1] - service[1])
        assert distance == 1


def test_default_layout_converts_to_grid_config():
    layout = create_default_warehouse_layout(num_agvs=3, max_episode_steps=128)

    grid_config = layout.to_grid_config(seed=7)

    assert grid_config.num_agents == 3
    assert grid_config.size == layout.size
    assert grid_config.map == layout.map
    assert grid_config.agents_xy == layout.agv_starts
    assert grid_config.max_episode_steps == 128
