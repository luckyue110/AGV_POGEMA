"""
A* + 优先级调度算法模块
"""

import heapq

from pogema import GridConfig
from pogema.envs import _make_pogema


def get_global_map_and_targets(grid_config: GridConfig):
    """从 GridConfig 中提取全局地图、起点和终点"""
    temp_env = _make_pogema(grid_config)
    temp_env.reset()
    inner = temp_env.unwrapped

    # 全局障碍物地图: 1=障碍, 0=可通行
    grid_map = inner.grid.get_obstacles()
    # 每个智能体的起点和终点, 坐标格式为 (row, col)
    starts = [tuple(pos) for pos in inner.grid.get_agents_xy()]
    targets = [tuple(pos) for pos in inner.grid.get_targets_xy()]
    temp_env.close()
    return grid_map, starts, targets


def astar(grid_map, start, goal, occupied_paths, agent_priority):
    """
    A* 寻路，考虑高优先级智能体已规划路径的时空冲突
    grid_map: 2D list, grid_map[row][col], 1=障碍, 0=可通行
    start: (row, col)
    goal: (row, col)
    occupied_paths: dict, {(row, col, t): agent_id}
    返回: [(row, col), ...] 路径（含起点）
    """
    rows, cols = len(grid_map), len(grid_map[0])
    # POGEMA MOVES: 0=静止[0,0], 1=上[-1,0], 2=下[1,0], 3=左[0,-1], 4=右[0,1]
    moves = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]
    max_t = rows * cols * 2  # 防止无限搜索

    def heuristic(pos, goal):
        return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])

    # (f, g, t, row, col)
    open_set = [(heuristic(start, goal), 0, 0, start[0], start[1])]
    visited = set()
    came_from = {}

    while open_set:
        f, g, t, r, c = heapq.heappop(open_set)

        if (r, c) == goal:
            path = [(r, c)]
            state = (r, c, t)
            while state in came_from:
                state = came_from[state]
                path.append((state[0], state[1]))
            path.reverse()
            return path

        if (r, c, t) in visited:
            continue
        visited.add((r, c, t))

        if t >= max_t:
            continue

        for dr, dc in moves:
            nr, nc, nt = r + dr, c + dc, t + 1
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if grid_map[nr][nc] == 1:
                continue
            if (nr, nc, nt) in occupied_paths:
                continue
            # 交换冲突检查
            if (r, c, nt) in occupied_paths and (nr, nc, t) in occupied_paths:
                if occupied_paths[(r, c, nt)] == occupied_paths[(nr, nc, t)]:
                    continue
            if (nr, nc, nt) not in visited:
                new_g = g + 1
                new_f = new_g + heuristic((nr, nc), goal)
                heapq.heappush(open_set, (new_f, new_g, nt, nr, nc))
                if (nr, nc, nt) not in came_from:
                    came_from[(nr, nc, nt)] = (r, c, t)

    # 找不到路径，返回原地等待
    return [start]


def priority_planning(grid_map, starts, targets):
    """
    优先级调度: 按顺序为每个智能体规划路径，后规划的避让先规划的
    返回: paths[agent_id] = [(row,col), ...]
    """
    occupied = {}  # (row, col, t) -> agent_id
    paths = []

    for agent_id in range(len(starts)):
        path = astar(grid_map, starts[agent_id], targets[agent_id], occupied, agent_id)
        paths.append(path)

        for t, (r, c) in enumerate(path):
            occupied[(r, c, t)] = agent_id
        # 到达目标后，智能体停在原地
        last_pos = path[-1]
        for t in range(len(path), len(path) + 100):
            occupied[(last_pos[0], last_pos[1], t)] = agent_id

    return paths


def path_to_actions(path):
    """
    将 (row, col) 路径序列转换为 POGEMA 动作序列
    POGEMA MOVES: 0=静止, 1=上, 2=下, 3=左, 4=右
    """
    move_to_action = {
        (0, 0): 0,
        (-1, 0): 1,
        (1, 0): 2,
        (0, -1): 3,
        (0, 1): 4,
    }
    actions = []
    for i in range(len(path) - 1):
        dr = path[i + 1][0] - path[i][0]
        dc = path[i + 1][1] - path[i][1]
        actions.append(move_to_action.get((dr, dc), 0))
    return actions
