"""
结果保存工具：动画保存 + 日志记录
"""

import logging
import os
from datetime import datetime


def setup_logger(case_name: str, log_dir: str = "outputs/logs") -> logging.Logger:
    """
    初始化 logger，同时输出到控制台和日志文件
    log_dir/case_name_YYYYMMDD_HHMMSS.log
    """
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{case_name}_{timestamp}.log")

    logger = logging.getLogger(case_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    )

    # 文件 handler
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 控制台 handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"日志文件: {log_path}")
    return logger


def save_animation(env, case_name: str, anim_dir: str = "outputs/animations") -> str:
    """
    保存 SVG 动画到 outputs/animations/<case_name>.svg
    返回保存路径
    """
    os.makedirs(anim_dir, exist_ok=True)
    out_path = os.path.join(anim_dir, f"{case_name}.svg")
    env.save_animation(out_path)
    return out_path


def log_run_summary(
    logger: logging.Logger,
    case_name: str,
    steps: int,
    total_reward: float,
    terminated: list,
    blocked_count: list,
    paths: list,
):
    """打印并记录一次仿真运行的汇总信息"""
    n = len(terminated)
    success = all(terminated)

    logger.info("=" * 50)
    logger.info(f"测试用例: {case_name}")
    logger.info(f"仿真步数: {steps}")
    logger.info(f"总奖励:   {total_reward:.2f}")
    logger.info(f"结束原因: {'所有智能体到达目标 ✓' if success else '达到最大步数 ✗'}")
    logger.info("-" * 50)
    for i in range(n):
        status = "✓ 到达" if terminated[i] else "✗ 未到达"
        logger.info(
            f"  Agent {i}: {status} | 路径长={len(paths[i])} | 阻塞次数={blocked_count[i]}"
        )
    logger.info("=" * 50)
