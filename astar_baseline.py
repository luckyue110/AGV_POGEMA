"""
A* + 优先级调度 Baseline 主入口

用法:
    python astar_baseline.py                   # 运行所有测试用例
    python astar_baseline.py --case crossroad  # 只运行指定用例
    python astar_baseline.py --list            # 列出所有可用用例
"""

import argparse

from pogema import AnimationConfig, AnimationMonitor
from pogema.envs import _make_pogema

from algorithms.astar import (
    get_global_map_and_targets,
    path_to_actions,
    priority_planning,
)
from test.cases.map import ALL_CASES
from utils.result_saver import log_run_summary, save_animation, setup_logger

MOVE_DELTA = {0: (0, 0), 1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}


def run_case(case_name: str, grid_config):
    logger = setup_logger(f"astar_{case_name}")
    logger.info(f"========== 开始用例: {case_name} ==========")

    # 1. 离线规划
    grid_map, starts, targets = get_global_map_and_targets(grid_config)
    logger.info(
        f"地图大小: {len(grid_map[0])} x {len(grid_map)} | Agent数: {len(starts)}"
    )
    for i, (s, t) in enumerate(zip(starts, targets)):
        logger.debug(f"  Agent {i}: {s} -> {t}")

    paths = priority_planning(grid_map, starts, targets)
    for i, p in enumerate(paths):
        logger.info(f"  Agent {i} 规划路径长度: {len(p)}")

    all_actions = [path_to_actions(p) for p in paths]

    # 2. 在 POGEMA 环境中执行
    anim_cfg = AnimationConfig(
        directory="outputs/animations",
        static=False,
        show_agents=True,
    )
    env = _make_pogema(grid_config)
    env = AnimationMonitor(env, animation_config=anim_cfg)
    obs, info = env.reset()
    inner_env = env.unwrapped

    agent_action_t = [0] * grid_config.num_agents
    blocked_count = [0] * grid_config.num_agents
    step = 0
    total_reward = 0.0
    terminated = [False] * grid_config.num_agents

    for t in range(grid_config.max_episode_steps):
        actions = [
            all_actions[i][agent_action_t[i]]
            if agent_action_t[i] < len(all_actions[i])
            else 0
            for i in range(grid_config.num_agents)
        ]

        positions_before = [tuple(pos) for pos in inner_env.grid.get_agents_xy()]
        obs, rewards, terminated, truncated, infos = env.step(actions)
        positions_after = [tuple(pos) for pos in inner_env.grid.get_agents_xy()]

        for i in range(grid_config.num_agents):
            if terminated[i]:
                continue
            if actions[i] != 0 and positions_after[i] == positions_before[i]:
                blocked_count[i] += 1
                dr, dc = MOVE_DELTA[actions[i]]
                r, c = positions_before[i]
                logger.debug(
                    f"  [t={t}] Agent {i} 阻塞! "
                    f"期望({r + dr},{c + dc}) 实际停在{positions_after[i]}"
                )
            else:
                agent_action_t[i] += 1

        step += 1
        total_reward += sum(rewards)
        if all(terminated) or all(truncated):
            break

    # 3. 保存结果
    out_path = save_animation(env, f"astar_{case_name}")
    log_run_summary(
        logger, case_name, step, total_reward, list(terminated), blocked_count, paths
    )
    logger.info(f"动画已保存: {out_path}")
    env.close()


def main():
    parser = argparse.ArgumentParser(description="A* + 优先级调度 Baseline")
    parser.add_argument("--case", type=str, default=None, help="指定运行的测试用例名称")
    parser.add_argument("--list", action="store_true", help="列出所有可用测试用例")
    args = parser.parse_args()

    if args.list:
        print("可用测试用例:")
        for name, cfg in ALL_CASES.items():
            print(f"  {name:<12} agents={cfg.num_agents}, size={cfg.size}")
        return

    if args.case:
        if args.case not in ALL_CASES:
            print(f"[错误] 未知用例 \\'{args.case}\\'，可用: {list(ALL_CASES.keys())}")
            return
        cases_to_run = {args.case: ALL_CASES[args.case]}
    else:
        cases_to_run = ALL_CASES

    for case_name, grid_config in cases_to_run.items():
        run_case(case_name, grid_config)


if __name__ == "__main__":
    main()
