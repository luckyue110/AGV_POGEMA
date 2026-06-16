from pogema import GridConfig

# 对穿冲突: Agent0 向右走，Agent1 向左走，路径交叉
gc_swap = GridConfig(
    num_agents=2,
    size=8,
    map=[
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    starts_xy=[(1, 3), (5, 3)],  # Agent0在左，Agent1在右
    targets_xy=[(5, 3), (1, 3)],  # 目标互换
    max_episode_steps=64,
    seed=42,
)

# 顶点冲突: 两Agent从两个方向同时冲向同一格
gc_vertex = GridConfig(
    num_agents=2,
    size=8,
    map=[[0] * 8 for _ in range(8)],
    starts_xy=[(1, 3), (3, 3)],  # 左右各一个，中间格(2,3)是必经之路
    targets_xy=[
        (5, 3),
        (5, 3),
    ],  # 同一个目标（POGEMA允许不同Agent有不同目标，这里设同列不同行）
    max_episode_steps=64,
    seed=42,
)
# 更典型的写法：两Agent从正上和正左同时冲向(3,3)
gc_vertex2 = GridConfig(
    num_agents=2,
    size=8,
    map=[[0] * 8 for _ in range(8)],
    starts_xy=[(3, 1), (1, 3)],  # Agent0在上方，Agent1在左方
    targets_xy=[(3, 6), (6, 3)],  # 路径必然在(3,3)附近交叉
    max_episode_steps=64,
    seed=42,
)


# 死锁: 一字形窄走廊，两端各一Agent，中间只有一格宽
# 图示: A0→→→ | ←←←A1  走廊宽=1，无法让路
gc_deadlock = GridConfig(
    num_agents=2,
    size=8,
    map=[
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 0, 1],  # 单行走廊
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
    ],
    starts_xy=[(1, 1), (5, 1)],  # 走廊两端
    targets_xy=[(5, 1), (1, 1)],  # 目标互换
    max_episode_steps=64,
    seed=42,
)


# 跟随冲突: 3个Agent排队，前方有障碍物死胡同
gc_follow = GridConfig(
    num_agents=3,
    size=8,
    map=[
        [1, 1, 1, 1, 0, 1, 1, 1],
        [1, 0, 0, 0, 0, 1, 1, 1],  # 横向走廊 col 1~4
        [1, 1, 1, 1, 0, 1, 1, 1],  # 死胡同 col 4, row 2
        [1, 1, 1, 1, 0, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
    ],
    starts_xy=[(1, 1), (2, 1), (3, 1)],  # 三Agent排队
    targets_xy=[
        (4, 2),
        (4, 1),
        (4, 3),
    ],  # 目标各不同，前两个在走廊末端
    max_episode_steps=64,
    seed=42,
)

# 十字路口冲突
gc_crossroad = GridConfig(
    num_agents=4,
    size=8,
    map=[
        [1, 1, 1, 0, 1, 1, 1, 1],
        [1, 1, 1, 0, 1, 1, 1, 1],
        [1, 1, 1, 0, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 0, 0, 1],  # 横向走廊
        [1, 1, 1, 0, 1, 1, 1, 1],
        [1, 1, 1, 0, 1, 1, 1, 1],
        [1, 1, 1, 0, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1],
    ],
    starts_xy=[(3, 0), (3, 6), (0, 3), (3, 5)],  # 四个方向各来一个
    targets_xy=[(3, 6), (3, 0), (3, 5), (0, 3)],  # 目标在对面
    max_episode_steps=128,
    seed=42,
)

# 随机大地图
gc_random = GridConfig(
    num_agents=10,
    size=16,
    density=0.2,
    seed=42,
    max_episode_steps=256,
    obs_radius=5,
)

# 统一注册，key 即为输出文件名前缀
ALL_CASES = {
    "swap": gc_swap,
    "vertex": gc_vertex2,
    "deadlock": gc_deadlock,
    "follow": gc_follow,
    "crossroad": gc_crossroad,
    "random": gc_random,
}
