import html
import os
import re

from warehouse.layouts import Coordinate, WarehouseLayout
from warehouse.scheduler import ScheduleResult
from warehouse.tasks import TransportTask

CELL = 34
MARGIN = 28
LEGEND_WIDTH = 360

ROUTE_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2"]


def save_route_map_svg(
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    out_path: str = "outputs/animations/warehouse_route_map.svg",
) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    svg = build_route_map_svg(layout, tasks, schedule, paths)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write(svg)
    return out_path


def save_solution_animation_svg(
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    out_path: str = "outputs/animations/warehouse_solution_animated.svg",
) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    svg = build_solution_animation_svg(layout, tasks, schedule, paths)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write(svg)
    return out_path


def save_enhanced_pogema_svg(
    base_svg_path: str,
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    out_path: str = "outputs/animations/warehouse_agv_enhanced.svg",
    overlay_paths: list[list[Coordinate]] | None = None,
) -> str:
    with open(base_svg_path, "r", encoding="utf-8") as file:
        original_svg = file.read()
    enhanced = build_enhanced_pogema_svg(
        original_svg, layout, tasks, schedule, paths, overlay_paths=overlay_paths
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as file:
        file.write(enhanced)
    return out_path


def build_enhanced_pogema_svg(
    original_svg: str,
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    overlay_paths: list[list[Coordinate]] | None = None,
) -> str:
    duration = _extract_pogema_duration(original_svg)
    original_svg = _remove_pogema_visibility_hiding(original_svg)
    original_svg = _convert_pogema_agent_motion_to_transform(
        original_svg, paths, overlay_paths, duration
    )
    overlay = _build_pogema_intent_overlay(
        layout, tasks, schedule, paths, duration, overlay_paths=overlay_paths
    )
    if "</svg>" not in original_svg:
        return original_svg + overlay
    return original_svg.replace("</svg>", overlay + "\n</svg>", 1)


def _convert_pogema_agent_motion_to_transform(
    svg: str,
    paths: list[list[Coordinate]],
    overlay_paths: list[list[Coordinate]] | None,
    duration: float,
) -> str:
    agent_paths = _normalize_overlay_paths(paths, overlay_paths)
    agent_index = 0

    def replace_agent(match: re.Match) -> str:
        nonlocal agent_index
        if agent_index >= len(agent_paths) or not agent_paths[agent_index]:
            agent_index += 1
            return match.group(0)

        markup = match.group(0)
        path = agent_paths[agent_index]
        agent_index += 1

        markup = re.sub(r'\s+cx="[^"]*"', ' cx="0"', markup, count=1)
        markup = re.sub(r'\s+cy="[^"]*"', ' cy="0"', markup, count=1)
        markup = re.sub(
            r'<animate\s+attributeName="(?:cx|cy)"[^>]*/>\s*',
            "",
            markup,
        )
        xs, ys = _pogema_path_values(path)
        key_times = _svg_key_times(len(path))
        transform = _animate_translate(xs, ys, key_times, duration)
        return markup.replace("</circle>", transform + "</circle>", 1)

    return re.sub(
        r'<circle\b(?=[^>]*class="agent")[^>]*>.*?</circle>',
        replace_agent,
        svg,
        flags=re.DOTALL,
    )


def _remove_pogema_visibility_hiding(svg: str) -> str:
    return re.sub(
        r"<animate\s+attributeName=\"visibility\"[^>]*/>\s*",
        "",
        svg,
    )


def _extract_pogema_duration(svg: str) -> float:
    match = re.search(r'dur="([0-9]+(?:\.[0-9]+)?)s"', svg)
    if not match:
        return 8.0
    return float(match.group(1))


def build_route_map_svg(
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
) -> str:
    grid_size = layout.size * CELL
    width = MARGIN * 2 + grid_size + LEGEND_WIDTH
    height = max(MARGIN * 2 + grid_size, 620)
    legend_x = MARGIN + grid_size + 34

    parts = [
        _svg_header(width, height),
        f'<text x="{MARGIN}" y="24" class="title">Warehouse AGV Route Map</text>',
        _draw_grid_background(layout),
        _draw_station_points(layout.station_points),
        _draw_cargo_shelves(layout.shelf_points),
        _draw_named_points(layout.pickup_points, "pickup"),
        _draw_named_points(layout.dropoff_points, "dropoff"),
        _draw_agv_starts(layout),
        _draw_routes(paths),
        _draw_legend(legend_x, 46, tasks, schedule, paths),
        "</svg>",
    ]
    return "\n".join(parts)


def _build_pogema_intent_overlay(
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    duration: float,
    overlay_paths: list[list[Coordinate]] | None = None,
) -> str:
    cargo_paths = _normalize_overlay_paths(paths, overlay_paths)
    parts = [
        """
<g id="pogema-intent-overlay">
<style>
  .intent-label { font: 700 34px Arial, sans-serif; paint-order: stroke; stroke: white; stroke-width: 7; fill: #1f2937; }
  .intent-small { font: 28px Arial, sans-serif; paint-order: stroke; stroke: white; stroke-width: 6; fill: #334155; }
  .intent-pickup { fill: #fef3c7; stroke: #b45309; stroke-width: 8; opacity: 0.88; }
  .intent-dropoff { fill: #dcfce7; stroke: #15803d; stroke-width: 8; opacity: 0.88; }
  .intent-cargo { stroke: #111827; stroke-width: 5; }
</style>
""".strip()
    ]
    parts.append(_draw_pogema_static_locations(layout, tasks))
    parts.append(_draw_pogema_cargo_overlays(schedule, cargo_paths, duration))
    parts.append(_draw_pogema_overlay_legend(schedule, tasks))
    parts.append("</g>")
    return "\n".join(parts)


def _normalize_overlay_paths(
    paths: list[list[Coordinate]], overlay_paths: list[list[Coordinate]] | None
) -> list[list[Coordinate]]:
    if overlay_paths is None:
        return paths

    normalized = []
    for index, path in enumerate(paths):
        if index < len(overlay_paths) and overlay_paths[index]:
            normalized.append(overlay_paths[index])
        else:
            normalized.append(path)
    return normalized


def _draw_pogema_static_locations(
    layout: WarehouseLayout, tasks: list[TransportTask]
) -> str:
    used_pickups = {task.pickup_name: task.pickup for task in tasks}
    used_dropoffs = {task.dropoff_name: task.dropoff for task in tasks}
    destination_tasks: dict[str, list[str]] = {}
    for task in tasks:
        destination_tasks.setdefault(task.dropoff_name, []).append(task.task_id)

    parts = []
    for name, coord in sorted(layout.station_points.items()):
        x, y = _pogema_center(layout, coord)
        parts.append(
            f'<rect x="{x - 42}" y="{y - 42}" width="84" height="84" rx="10" fill="#64748b" stroke="#0f172a" stroke-width="7" opacity="0.9">'
            f'<title>station {html.escape(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 10}" text-anchor="middle" class="intent-label">ST {html.escape(name)}</text>'
        )
    for name, coord in sorted(layout.shelf_points.items()):
        x, y = _pogema_center(layout, coord)
        parts.append(
            f'<rect x="{x - 30}" y="{y - 30}" width="60" height="60" rx="8" fill="#f97316" stroke="#7c2d12" stroke-width="6" opacity="0.95">'
            f'<title>cargo shelf {html.escape(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 8}" text-anchor="middle" class="intent-label">{html.escape(name)}</text>'
        )
    for name, coord in sorted(used_pickups.items()):
        x, y = _pogema_center(layout, coord)
        parts.append(
            f'<rect x="{x - 38}" y="{y - 38}" width="76" height="76" rx="14" class="intent-pickup">'
            f'<title>pickup {html.escape(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 10}" text-anchor="middle" class="intent-label">P {html.escape(name)}</text>'
        )

    for name, coord in sorted(used_dropoffs.items()):
        x, y = _pogema_center(layout, coord)
        task_ids = ",".join(destination_tasks.get(name, []))
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="46" class="intent-dropoff">'
            f'<title>dropoff {html.escape(name)} cargo destination {html.escape(task_ids)}</title></circle>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 10}" text-anchor="middle" class="intent-label">D {html.escape(name)}</text>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 56}" text-anchor="middle" class="intent-small">cargo destination {html.escape(task_ids)}</text>'
        )
    return "\n".join(parts)


def _draw_pogema_cargo_overlays(
    schedule: ScheduleResult, paths: list[list[Coordinate]], duration: float
) -> str:
    parts = []
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        if not path:
            continue
        color = ROUTE_COLORS[agv_schedule.agv_id % len(ROUTE_COLORS)]
        xs, ys = _pogema_path_values(path)
        key_times = _svg_key_times(len(path))
        for task_index, task in enumerate(agv_schedule.tasks):
            parts.append(
                f'<g><rect x="-24" y="-24" width="48" height="48" rx="8" fill="{color}" class="intent-cargo">'
                f'<title>cargo loaded {html.escape(task.task_id)} destination {html.escape(task.dropoff_name)}</title>'
                f'{_opacity_animation(_loaded_windows(path, agv_schedule, task_index), len(path), duration)}'
                "</rect>"
                f'<text x="0" y="10" text-anchor="middle" class="intent-label">{html.escape(task.task_id)}</text>'
                f'{_opacity_animation(_loaded_windows(path, agv_schedule, task_index), len(path), duration)}'
                f'{_animate_translate(xs, ys, key_times, duration)}'
                "</g>"
            )
    return "\n".join(parts)


def _draw_pogema_overlay_legend(
    schedule: ScheduleResult, tasks: list[TransportTask]
) -> str:
    x = 80
    y = -1760
    parts = [
        f'<rect x="{x - 30}" y="{y - 60}" width="720" height="260" rx="24" fill="white" opacity="0.86" stroke="#94a3b8" stroke-width="5" />',
        f'<text x="{x}" y="{y}" class="intent-label">Enhanced POGEMA view</text>',
        f'<text x="{x}" y="{y + 48}" class="intent-small">original circle = no cargo, solid box = cargo loaded</text>',
        f'<text x="{x}" y="{y + 92}" class="intent-small">P = pickup, D = dropoff / cargo destination</text>',
    ]
    y += 138
    for agv_schedule in schedule.agv_schedules:
        color = ROUTE_COLORS[agv_schedule.agv_id % len(ROUTE_COLORS)]
        task_ids = ",".join(task.task_id for task in agv_schedule.tasks) or "idle"
        parts.append(
            f'<text x="{x}" y="{y}" class="intent-small" fill="{color}">AGV {agv_schedule.agv_id}: {html.escape(task_ids)}</text>'
        )
        y += 34
    return "\n".join(parts)


def build_solution_animation_svg(
    layout: WarehouseLayout,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
) -> str:
    grid_size = layout.size * CELL
    width = MARGIN * 2 + grid_size + LEGEND_WIDTH
    height = max(MARGIN * 2 + grid_size, 660)
    legend_x = MARGIN + grid_size + 34
    max_steps = max((len(path) for path in paths), default=1)
    duration = max(8, max_steps * 0.16)

    parts = [
        _svg_header(width, height),
        f'<text x="{MARGIN}" y="24" class="title">Animated Warehouse AGV Solution</text>',
        _draw_grid_background(layout),
        _draw_station_points(layout.station_points),
        _draw_cargo_shelves(layout.shelf_points),
        _draw_named_points(layout.pickup_points, "pickup"),
        _draw_named_points(layout.dropoff_points, "dropoff"),
        _draw_destination_badges(tasks),
        _draw_routes(paths),
        _draw_agv_animation(schedule, paths, duration),
        _draw_animation_legend(legend_x, 46, tasks, schedule, paths, duration),
        "</svg>",
    ]
    return "\n".join(parts)


def _svg_header(width: int, height: int) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
  .title {{ font: 700 18px Arial, sans-serif; fill: #111827; }}
  .cell {{ stroke: #d1d5db; stroke-width: 1; }}
  .free {{ fill: #f8fafc; }}
  .shelf {{ fill: #334155; }}
  .pickup {{ fill: #fde68a; stroke: #92400e; stroke-width: 1.5; }}
  .dropoff {{ fill: #bbf7d0; stroke: #166534; stroke-width: 1.5; }}
  .start {{ fill: #bfdbfe; stroke: #1d4ed8; stroke-width: 1.5; }}
  .label {{ font: 700 9px Arial, sans-serif; fill: #111827; text-anchor: middle; dominant-baseline: central; }}
  .small {{ font: 12px Arial, sans-serif; fill: #374151; }}
  .legend-title {{ font: 700 14px Arial, sans-serif; fill: #111827; }}
  .route {{ fill: none; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; opacity: 0.74; }}
</style>'''


def _draw_grid_background(layout: WarehouseLayout) -> str:
    parts = []
    for row, line in enumerate(layout.map):
        for col, value in enumerate(line):
            x, y = _cell_origin((row, col))
            klass = "shelf" if value == 1 else "free"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" class="cell {klass}" />'
            )
    return "\n".join(parts)


def _draw_named_points(points: dict[str, Coordinate], klass: str) -> str:
    parts = []
    for name, coord in sorted(points.items()):
        x, y = _cell_origin(coord)
        parts.append(
            f'<rect x="{x + 4}" y="{y + 4}" width="{CELL - 8}" height="{CELL - 8}" rx="4" class="{klass}" />'
        )
        parts.append(f'<text x="{x + CELL / 2}" y="{y + CELL / 2}" class="label">{html.escape(name)}</text>')
    return "\n".join(parts)


def _draw_station_points(points: dict[str, Coordinate]) -> str:
    parts = []
    for name, coord in sorted(points.items()):
        x, y = _cell_origin(coord)
        parts.append(
            f'<rect x="{x + 3}" y="{y + 3}" width="{CELL - 6}" height="{CELL - 6}" rx="3" fill="#64748b" stroke="#0f172a" stroke-width="2">'
            f'<title>station {html.escape(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{x + CELL / 2}" y="{y + CELL / 2}" class="label">{html.escape(name)}</text>'
        )
    return "\n".join(parts)


def _draw_cargo_shelves(points: dict[str, Coordinate]) -> str:
    parts = []
    for name, coord in sorted(points.items()):
        x, y = _cell_origin(coord)
        parts.append(
            f'<rect x="{x + 8}" y="{y + 8}" width="{CELL - 16}" height="{CELL - 16}" rx="4" fill="#f97316" stroke="#7c2d12" stroke-width="2">'
            f'<title>cargo shelf {html.escape(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{x + CELL / 2}" y="{y + CELL / 2}" class="label">{html.escape(name)}</text>'
        )
    return "\n".join(parts)


def _draw_agv_starts(layout: WarehouseLayout) -> str:
    parts = []
    for agv_id, coord in enumerate(layout.agv_starts):
        cx, cy = _cell_center(coord)
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="11" class="start" />')
        parts.append(f'<text x="{cx}" y="{cy}" class="label">A{agv_id}</text>')
    return "\n".join(parts)


def _draw_routes(paths: list[list[Coordinate]]) -> str:
    parts = []
    for agv_id, path in enumerate(paths):
        if len(path) < 2:
            continue
        color = ROUTE_COLORS[agv_id % len(ROUTE_COLORS)]
        points = " ".join(f"{x},{y}" for x, y in (_cell_center(coord) for coord in path))
        parts.append(f'<polyline points="{points}" class="route" stroke="{color}" />')
    return "\n".join(parts)


def _draw_agv_animation(
    schedule: ScheduleResult, paths: list[list[Coordinate]], duration: float
) -> str:
    parts = []
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        if not path:
            continue
        color = ROUTE_COLORS[agv_schedule.agv_id % len(ROUTE_COLORS)]
        motion_path = _motion_path(path)
        parts.append(
            f'<circle r="9" fill="{color}" stroke="#111827" stroke-width="1.2">'
            f'<animateMotion dur="{duration:.2f}s" path="{motion_path}" fill="freeze" repeatCount="indefinite" />'
            "</circle>"
        )
        parts.append(
            f'<polygon points="0,-7 7,0 0,7 -7,0" fill="white" stroke="{color}" stroke-width="2">'
            f'<animateMotion dur="{duration:.2f}s" path="{motion_path}" fill="freeze" repeatCount="indefinite" />'
            f'{_opacity_animation(_empty_windows(path, agv_schedule), len(path), duration)}'
            "</polygon>"
        )
        for task_index, task in enumerate(agv_schedule.tasks):
            parts.append(
                f'<rect x="-6" y="-6" width="12" height="12" rx="2" fill="{color}" stroke="#111827" stroke-width="1">'
                f'<animateMotion dur="{duration:.2f}s" path="{motion_path}" fill="freeze" repeatCount="indefinite" />'
                f'{_opacity_animation(_loaded_windows(path, agv_schedule, task_index), len(path), duration)}'
                f'<title>loaded AGV {agv_schedule.agv_id} carrying {html.escape(task.task_id)} to {html.escape(task.dropoff_name)}</title>'
                "</rect>"
            )
    return "\n".join(parts)


def _draw_destination_badges(tasks: list[TransportTask]) -> str:
    by_destination: dict[Coordinate, list[str]] = {}
    for task in tasks:
        by_destination.setdefault(task.dropoff, []).append(task.task_id)

    parts = []
    for coord, task_ids in by_destination.items():
        cx, cy = _cell_center(coord)
        text = ",".join(task_ids)
        parts.append(
            f'<text x="{cx}" y="{cy + 22}" class="label">dest {html.escape(text)}</text>'
        )
    return "\n".join(parts)


def _draw_animation_legend(
    x: int,
    y: int,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
    duration: float,
) -> str:
    parts = [
        f'<text x="{x}" y="{y}" class="legend-title">Animated legend</text>',
        f'<circle cx="{x + 8}" cy="{y + 28}" r="8" fill="#2563eb" stroke="#111827" />',
        f'<text x="{x + 28}" y="{y + 32}" class="small">AGV body: same color per vehicle</text>',
        f'<rect x="{x + 2}" y="{y + 48}" width="12" height="12" rx="2" fill="#2563eb" stroke="#111827" />',
        f'<text x="{x + 28}" y="{y + 60}" class="small">loaded AGV: solid cargo box</text>',
        f'<text x="{x}" y="{y + 90}" class="small">cargo destination labels appear near stations</text>',
        f'<text x="{x}" y="{y + 114}" class="small">animation duration: {duration:.1f}s loop</text>',
    ]
    y += 146
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        color = ROUTE_COLORS[agv_schedule.agv_id % len(ROUTE_COLORS)]
        task_ids = ", ".join(task.task_id for task in agv_schedule.tasks) or "idle"
        parts.append(f'<line x1="{x}" y1="{y - 4}" x2="{x + 26}" y2="{y - 4}" stroke="{color}" stroke-width="4" />')
        parts.append(
            f'<text x="{x + 36}" y="{y}" class="small">AGV {agv_schedule.agv_id}: {html.escape(task_ids)} | steps={len(path)}</text>'
        )
        y += 20

    y += 12
    parts.append(f'<text x="{x}" y="{y}" class="legend-title">Task destinations</text>')
    y += 22
    for task in tasks:
        parts.append(
            f'<text x="{x}" y="{y}" class="small">{html.escape(task.task_id)}: '
            f'{html.escape(task.pickup_name)} cargo destination {html.escape(task.dropoff_name)}</text>'
        )
        y += 18
    return "\n".join(parts)


def _draw_legend(
    x: int,
    y: int,
    tasks: list[TransportTask],
    schedule: ScheduleResult,
    paths: list[list[Coordinate]],
) -> str:
    parts = [f'<text x="{x}" y="{y}" class="legend-title">Tasks and AGV routes</text>']
    y += 26
    for agv_schedule, path in zip(schedule.agv_schedules, paths):
        color = ROUTE_COLORS[agv_schedule.agv_id % len(ROUTE_COLORS)]
        task_ids = ", ".join(task.task_id for task in agv_schedule.tasks) or "idle"
        parts.append(f'<line x1="{x}" y1="{y - 4}" x2="{x + 26}" y2="{y - 4}" stroke="{color}" stroke-width="4" />')
        parts.append(
            f'<text x="{x + 36}" y="{y}" class="small">AGV {agv_schedule.agv_id}: {html.escape(task_ids)} | edges={max(len(path) - 1, 0)}</text>'
        )
        y += 22

    y += 14
    parts.append(f'<text x="{x}" y="{y}" class="legend-title">Task details</text>')
    y += 24
    for task in tasks:
        parts.append(
            f'<text x="{x}" y="{y}" class="small">{html.escape(task.task_id)}: '
            f'{html.escape(task.pickup_name)} -> {html.escape(task.dropoff_name)}</text>'
        )
        y += 19
    return "\n".join(parts)


def _motion_path(path: list[Coordinate]) -> str:
    points = [_cell_center(coord) for coord in path]
    first_x, first_y = points[0]
    commands = [f"M {first_x:.1f} {first_y:.1f}"]
    commands.extend(f"L {x:.1f} {y:.1f}" for x, y in points[1:])
    return " ".join(commands)


def _pogema_center(layout: WarehouseLayout, coord: Coordinate) -> tuple[float, float]:
    row, col = coord
    x = (col + 2) * 100
    y = -((layout.size - row + 1) * 100)
    return float(x), float(y)


def _pogema_path_values(path: list[Coordinate]) -> tuple[list[str], list[str]]:
    # POGEMA pads the user map with a two-cell border in the rendered SVG.
    # For a layout cell (row, col), the rendered center is:
    # x=(col+2)*100, y=-(layout_size-row+1)*100.
    size = 16
    xs = [str((col + 2) * 100) for row, col in path]
    ys = [str(-((size - row + 1) * 100)) for row, col in path]
    return xs, ys


def _svg_key_times(count: int) -> list[str]:
    if count <= 1:
        return ["0", "1"]
    return [f"{index / (count - 1):.6f}" for index in range(count)]


def _animate_translate(
    xs: list[str], ys: list[str], key_times: list[str], duration: float
) -> str:
    return (
        f'<animateTransform attributeName="transform" type="translate" dur="{duration:.2f}s" '
        f'repeatCount="indefinite" values="{";".join(f"{x} {y}" for x, y in zip(xs, ys))}" '
        f'keyTimes="{";".join(key_times)}" />'
    )


def _infer_pogema_duration(paths: list[list[Coordinate]]) -> float:
    max_steps = max((len(path) for path in paths), default=1)
    return max(8.0, (max_steps - 1) * 0.25)


def _loaded_windows(
    path: list[Coordinate], agv_schedule, task_index: int
) -> list[tuple[int, int]]:
    cursor = 0
    for index, task in enumerate(agv_schedule.tasks):
        pickup_index = _find_coord_index(path, task.pickup, cursor)
        dropoff_index = _find_coord_index(path, task.dropoff, pickup_index)
        if index == task_index:
            return [(pickup_index, dropoff_index)]
        cursor = dropoff_index + 1
    return []


def _empty_windows(path: list[Coordinate], agv_schedule) -> list[tuple[int, int]]:
    loaded = []
    cursor = 0
    for task in agv_schedule.tasks:
        pickup_index = _find_coord_index(path, task.pickup, cursor)
        dropoff_index = _find_coord_index(path, task.dropoff, pickup_index)
        loaded.append((pickup_index, dropoff_index))
        cursor = dropoff_index + 1

    windows = []
    start = 0
    for loaded_start, loaded_end in loaded:
        if start < loaded_start:
            windows.append((start, loaded_start))
        start = loaded_end
    if start < len(path) - 1:
        windows.append((start, len(path) - 1))
    if not windows:
        windows.append((0, len(path) - 1))
    return windows


def _find_coord_index(path: list[Coordinate], coord: Coordinate, start: int) -> int:
    for index in range(start, len(path)):
        if path[index] == coord:
            return index
    return len(path) - 1


def _opacity_animation(
    visible_windows: list[tuple[int, int]], path_length: int, duration: float
) -> str:
    if path_length <= 1:
        return '<animate attributeName="opacity" values="1" dur="1s" fill="freeze" />'

    samples = []
    for step in range(path_length):
        visible = any(start <= step <= end for start, end in visible_windows)
        samples.append("1" if visible else "0")
    key_times = [f"{step / (path_length - 1):.4f}" for step in range(path_length)]
    return (
        f'<animate attributeName="opacity" dur="{duration:.2f}s" repeatCount="indefinite" '
        f'values="{";".join(samples)}" keyTimes="{";".join(key_times)}" />'
    )


def _cell_origin(coord: Coordinate) -> tuple[int, int]:
    row, col = coord
    return MARGIN + col * CELL, MARGIN + row * CELL


def _cell_center(coord: Coordinate) -> tuple[float, float]:
    x, y = _cell_origin(coord)
    return x + CELL / 2, y + CELL / 2
