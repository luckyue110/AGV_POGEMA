from warehouse.layouts import create_default_warehouse_layout
from warehouse.planner import plan_scheduled_paths
from warehouse.scheduler import schedule_tasks_greedy
from warehouse.tasks import parse_task_spec
from warehouse.visualization import (
    build_enhanced_pogema_svg,
    build_route_map_svg,
    build_solution_animation_svg,
)


def test_build_route_map_svg_includes_layout_routes_and_tasks():
    layout = create_default_warehouse_layout()
    tasks = parse_task_spec("S1:OUTBOUND,S3:PACKING,S12:INBOUND", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    svg = build_route_map_svg(layout, tasks, schedule, paths)

    assert "<svg" in svg
    assert "Warehouse AGV Route Map" in svg
    assert "S1" in svg
    assert "cargo shelf S1" in svg
    assert "OUTBOUND" in svg
    assert "station OUTBOUND" in svg
    assert "AGV 0" in svg
    assert "T001" in svg
    assert "<polyline" in svg


def test_build_solution_animation_svg_explains_cargo_state_and_destinations():
    layout = create_default_warehouse_layout()
    tasks = parse_task_spec("S1:OUTBOUND,S3:PACKING", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    svg = build_solution_animation_svg(layout, tasks, schedule, paths)

    assert "<svg" in svg
    assert "Animated Warehouse AGV Solution" in svg
    assert "loaded AGV" in svg
    assert "cargo destination" in svg
    assert "T001" in svg
    assert "<animateMotion" in svg


def test_build_enhanced_pogema_svg_preserves_original_and_adds_intent_overlay():
    layout = create_default_warehouse_layout()
    tasks = parse_task_spec("S1:OUTBOUND,S3:PACKING", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)
    original = '<svg viewBox="0 -1900 1900 1900"><circle class="agent" /></svg>'

    svg = build_enhanced_pogema_svg(original, layout, tasks, schedule, paths)

    assert '<circle class="agent"' in svg
    assert "pogema-intent-overlay" in svg
    assert "pickup S1" in svg
    assert "dropoff OUTBOUND" in svg
    assert "cargo loaded" in svg
    assert "empty AGV" not in svg
    assert "cargo destination" in svg


def test_build_enhanced_pogema_svg_keeps_finished_agents_visible():
    original = (
        '<svg><circle class="agent">'
        '<animate attributeName="visibility" values="visible;hidden" />'
        "</circle></svg>"
    )
    layout = create_default_warehouse_layout()

    svg = build_enhanced_pogema_svg(original, layout, [], schedule_tasks_greedy(layout.map, [], []), [])

    assert 'attributeName="visibility"' not in svg
    assert "visible;hidden" not in svg


def test_build_enhanced_pogema_svg_uses_original_animation_duration():
    original = (
        '<svg><circle class="agent">'
        '<animate attributeName="cx" dur="21.5s" values="0;1" />'
        "</circle></svg>"
    )
    layout = create_default_warehouse_layout()
    tasks = parse_task_spec("S1:OUTBOUND", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    svg = build_enhanced_pogema_svg(original, layout, tasks, schedule, paths)

    assert 'dur="21.50s"' in svg


def test_build_enhanced_pogema_svg_can_use_executed_paths_for_cargo_overlay():
    original = (
        '<svg><circle class="agent">'
        '<animate attributeName="cx" dur="3s" values="0;1" />'
        "</circle></svg>"
    )
    layout = create_default_warehouse_layout()
    tasks = parse_task_spec("S1:OUTBOUND", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    planned_paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)
    executed_paths = [planned_paths[0][:2] + [planned_paths[0][1]] + planned_paths[0][2:]]

    svg = build_enhanced_pogema_svg(
        original,
        layout,
        tasks,
        schedule,
        planned_paths,
        overlay_paths=executed_paths,
    )

    repeated = _as_pogema_translate_value(layout, planned_paths[0][1])
    assert repeated in svg


def test_build_enhanced_pogema_svg_converts_agent_motion_to_transform_animation():
    original = (
        '<svg><circle class="agent" cx="300" cy="-300" fill="#c1433c" r="35">'
        '<animate attributeName="cy" dur="3s" values="-300;-400" />'
        '<animate attributeName="cx" dur="3s" values="300;400" />'
        "</circle></svg>"
    )
    layout = create_default_warehouse_layout(num_agvs=1)
    tasks = parse_task_spec("S1:OUTBOUND", layout)
    schedule = schedule_tasks_greedy(layout.map, layout.agv_starts, tasks)
    paths = plan_scheduled_paths(layout.map, schedule.agv_schedules)

    svg = build_enhanced_pogema_svg(original, layout, tasks, schedule, paths)

    agent_markup = svg.split("pogema-intent-overlay")[0]
    assert 'attributeName="cx"' not in agent_markup
    assert 'attributeName="cy"' not in agent_markup
    assert 'type="translate"' in agent_markup
    assert 'cx="0"' in agent_markup
    assert 'cy="0"' in agent_markup


def _as_pogema_translate_value(layout, coord):
    row, col = coord
    return f"{(col + 2) * 100} {-((layout.size - row + 1) * 100)}"
