# Current Planning Baseline

Date: 2026-06-17

This document records the current algorithm before adding full CBS.

## Strategy

Current planner: prioritized planning with replanning fallback.

Implementation entry point:

```text
warehouse/planner.py::plan_scheduled_paths
```

High-level flow:

1. Build one full path per AGV with A* and a space-time reservation table.
2. Include pickup wait, drop-off wait, turn wait, and return-to-parking behavior.
3. Detect vertex conflicts and swap conflicts after all paths are built.
4. Convert conflicts into per-agent constraints.
5. Replan the lower-priority AGV with the new constraint.
6. If constrained replanning is not feasible, insert a local wait as fallback.

This strategy is not full CBS. It is a prioritized replanning approach with a local wait fallback.

## Baseline Scenario

Command-equivalent parameters:

```text
AGVs: 8
Random tasks: 16
Seed: 23
Max episode steps: 3000
Operation wait: 3
Turn wait: 2
Dispatch gap: 12
Return parking: AGV start cells
Fallback parking: layout parking points
```

## Tasks

```text
T001: S18(7, 6) -> INBOUND(14, 8)
T002: S1(1, 3) -> PACKING(14, 11)
T003: S18(7, 6) -> OUTBOUND(14, 14)
T004: S20(7, 13) -> PACKING(14, 11)
T005: S2(1, 4) -> INBOUND(14, 8)
T006: S9(6, 3) -> INBOUND(14, 8)
T007: S17(7, 3) -> OUTBOUND(14, 14)
T008: S1(1, 3) -> INBOUND(14, 8)
T009: S5(1, 10) -> OUTBOUND(14, 14)
T010: S1(1, 3) -> INBOUND(14, 8)
T011: S11(6, 6) -> PACKING(14, 11)
T012: S23(12, 11) -> OUTBOUND(14, 14)
T013: S1(1, 3) -> PACKING(14, 11)
T014: S6(1, 11) -> PACKING(14, 11)
T015: S21(12, 4) -> OUTBOUND(14, 14)
T016: S10(6, 4) -> INBOUND(14, 8)
```

## Task Assignment

```text
AGV 0: T012, T009
AGV 1: T015, T016
AGV 2: T001, T007
AGV 3: T004, T008
AGV 4: T006, T010
AGV 5: T003, T005
AGV 6: T011, T002
AGV 7: T014, T013
```

## Baseline Metrics

```text
Path lengths: [95, 95, 109, 129, 159, 249, 198, 202]
Path edges:   [94, 94, 108, 128, 158, 248, 197, 201]
Wait steps:   [30, 46, 52, 68, 92, 178, 125, 127]
Makespan:     248
Sum of edges: 1228
```

## Validation

The baseline strategy produces no vertex conflicts and no swap conflicts for this scenario.
