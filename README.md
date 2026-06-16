# AGV POGEMA Warehouse Scheduler

基于 [POGEMA](https://github.com/AIRI-Institute/pogema) 的仓库 AGV 调度与路径规划示例项目。项目把原始多智能体寻路环境扩展成一个简化但可运行的真实仓库场景：货架、入库区、打包区、出库区、多个 AGV、随机/指定运输任务、取放货等待、转向耗时、回库停车、碰撞规避和 SVG 动画可视化。

## 功能概览

- 仓库地图：货架、站点、服务点、停车点均可配置。
- 任务系统：支持随机生成任务，也支持指定 `货架:目的地`。
- 调度策略：空闲 AGV 优先，每次给空闲 AGV 分配最近任务。
- 路径规划：A* + 时空预约表 + prioritized replanning。
- 约束支持：同格冲突、对向换位冲突、指定时间点禁止进入某格/某边。
- 操作耗时：取货/放货默认等待 `3` 个时间单位。
- 转向耗时：改变前进方向默认等待 `2` 个时间单位。
- 停车要求：任务完成后 AGV 返回出发点；如果冲突，会通过重规划/等待避让。
- 可视化：输出原始 POGEMA SVG、增强 SVG、路线图和独立方案动画。

## 环境安装

推荐使用 `uv`：

```powershell
uv sync --dev
```

运行测试：

```powershell
$env:UV_CACHE_DIR='.uv-cache'
uv run python -m pytest -q
```

## 快速运行

列出可用货架和站点：

```powershell
uv run python warehouse_simulation.py --list-locations
```

运行默认随机任务：

```powershell
uv run python warehouse_simulation.py
```

运行复杂示例，生成 8 台 AGV、16 个随机任务：

```powershell
uv run python warehouse_simulation.py `
  --agvs 8 `
  --random-tasks 16 `
  --seed 23 `
  --max-episode-steps 3000 `
  --operation-wait 3 `
  --turn-wait 2 `
  --dispatch-gap 12 `
  --route-map outputs/animations/warehouse_8agv_16tasks_route_map.svg `
  --solution-animation outputs/animations/warehouse_8agv_16tasks_solution.svg
```

指定任务运行：

```powershell
uv run python warehouse_simulation.py --tasks "S1:OUTBOUND,S3:PACKING,S12:INBOUND"
```

## 输出文件

常用输出位置：

- `outputs/animations/warehouse_agv.svg`：POGEMA 原始动画。
- `outputs/animations/warehouse_agv_enhanced.svg`：增强动画，显示货物、取货点、目的地等信息。
- `outputs/animations/warehouse_route_map.svg`：静态路线图。
- `outputs/animations/warehouse_solution_animated.svg`：独立绘制的方案动画。
- `outputs/logs/warehouse_agv_*.log`：任务分配、路径长度、阻塞次数等日志。

建议优先查看：

```text
outputs/animations/warehouse_agv_enhanced.svg
```

## 算法说明

核心代码在 `warehouse/planner.py`。

当前规划流程：

1. 调度器先为每台 AGV 生成任务序列。
2. 单车 A* 按任务顺序规划：
   - 出发点 -> 取货服务点
   - 取货等待
   - 取货服务点 -> 放货服务点
   - 放货等待
   - 最后回到出发停车点
3. A* 使用时空预约表避开已经规划好的 AGV。
4. 生成所有路径后扫描冲突：
   - vertex conflict：同一时间两个 AGV 在同一格。
   - swap conflict：两个 AGV 在同一时间对向交换位置。
5. 若发现冲突，将冲突转化为约束：
   - `("vertex", time, position)`
   - `("edge", time, from_position, to_position)`
6. 对低优先级 AGV 重新规划完整路径。
7. 若局部约束下无法重规划，则使用少量等待作为兜底。

这不是完整最优 CBS，而是更适合工程落地的 prioritized planning with replanning。它比“只插等待”的策略更少出现某台车走一步停一步的问题，同时仍能保证输出路径无同格/换位碰撞。

## 如何改造算法

### 1. 修改任务分配策略

入口在 `warehouse/scheduler.py`：

```python
schedule_tasks_greedy(...)
```

当前策略是：每次选择最早空闲的 AGV，并给它最近的任务。

你可以改成：

- 考虑拥堵成本。
- 考虑任务优先级。
- 按出库/入库波次批量分配。
- 用匈牙利算法做一轮全局任务匹配。

建议保持输出仍为：

```python
ScheduleResult(agv_schedules=[...], unassigned_tasks=[...])
```

这样后面的路径规划和可视化不用改。

### 2. 修改路径规划策略

入口在 `warehouse/planner.py`：

```python
plan_scheduled_paths(...)
```

常见改造点：

- `astar_with_reservations`：替换或增强 A*。
- `_resolve_path_collisions`：修改冲突后重规划策略。
- `_constraint_from_collision`：扩展约束类型。
- `_plan_single_agv_path`：改变单车任务链规划方式。

例如，如果你想接近完整 CBS，可以：

1. 把当前单一路径集合改成 CBS 节点。
2. 每个 CBS 节点保存：
   - 所有 AGV 路径
   - 约束集合
   - 总成本
3. 每次取总成本最低的节点。
4. 找第一个冲突。
5. 分裂成两个子节点，分别约束冲突的两个 AGV。
6. 只重规划被加约束的 AGV。
7. 直到无冲突。

当前项目已经具备 CBS 所需的几个基础组件：

- 冲突检测：`_first_path_collision`
- 约束表：`ConstraintTable`
- 约束 A*：`astar_with_reservations(..., constraints=...)`
- 单车重规划：`_plan_single_agv_path`

### 3. 修改仓库地图

入口在 `warehouse/layouts.py`：

```python
create_default_warehouse_layout(...)
```

可调整内容：

- `shelf_blocks`：货架障碍物块。
- `station_points`：入库、打包、出库站点。
- `agv_starts`：AGV 出发/停车点。
- `shelf_points` 和 `pickup_points`：货物所在货架与 AGV 可停靠取货的服务点。
- `dropoff_points`：站点旁边的放货服务点。

注意：

- 货架、站点本身是障碍物，AGV 不允许进入。
- pickup/dropoff 应该放在障碍物旁边的可通行格子。
- 如果新增更多 AGV，需要确保停车点不会把主通道完全堵死。

### 4. 修改可视化

入口在 `warehouse/visualization.py`。

常见改造：

- 修改货物图标样式。
- 修改 pickup/dropoff 标签。
- 增加任务编号、目标站点、当前状态。
- 调整 POGEMA 原始 SVG 的增强 overlay。

增强动画生成函数：

```python
save_enhanced_pogema_svg(...)
```

## 测试建议

修改算法后至少运行：

```powershell
uv run python -m pytest -q
```

重点测试：

```powershell
uv run python -m pytest test/test_warehouse_planner.py -q
```

复杂场景建议验证：

- 所有 AGV 都完成任务。
- 阻塞次数为 `0`。
- 无 vertex/swap conflict。
- 某一台 AGV 不应出现大量连续等待。

## 项目结构

```text
warehouse/
  layouts.py        # 仓库地图、货架、站点、停车点
  tasks.py          # 任务生成与任务解析
  scheduler.py      # AGV 任务调度
  planner.py        # A*、预约表、冲突检测、重规划
  visualization.py  # 路线图和 SVG 动画增强

warehouse_simulation.py  # 命令行入口
test/                    # pytest 测试
outputs/                 # 动画和日志输出
```

## 注意事项

- 当前算法偏工程示例，不保证全局最优。
- `collision_system="soft"` 用于让 POGEMA 动画忠实展示离线路径；真实避碰由 `warehouse/planner.py` 保证。
- 如果地图更复杂、AGV 更多，建议把当前 prioritized replanning 进一步升级为完整 CBS 或带拥堵代价的分层规划。
