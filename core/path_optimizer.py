"""
path_optimizer.py — Nearest-Neighbor (TSP) path sequence optimization.

Minimizes rapid travel distance between drawing strokes.
"""
from __future__ import annotations
from typing import List, Tuple
import math

Polyline = List[Tuple[float, float]]


def optimize_paths(polylines: List[Polyline]) -> List[Polyline]:
    """
    Sorts polylines using a greedy nearest-neighbor algorithm.
    Reverses strokes when doing so reduces travel distance.

    Args:
        polylines: original list of polyline strokes

    Returns:
        Reordered and direction-optimized list of strokes.
    """
    if not polylines:
        return []

    remaining = list(polylines)
    result: List[Polyline] = []

    # Start near origin
    current_pos: Tuple[float, float] = (0.0, 0.0)

    while remaining:
        best_idx = 0
        best_dist = float("inf")
        best_reversed = False

        for i, pl in enumerate(remaining):
            if not pl:
                continue
            d_start = _dist(current_pos, pl[0])
            d_end = _dist(current_pos, pl[-1])
            d = min(d_start, d_end)

            if d < best_dist:
                best_dist = d
                best_idx = i
                best_reversed = d_end < d_start

        chosen = remaining.pop(best_idx)
        if best_reversed:
            chosen = list(reversed(chosen))

        result.append(chosen)
        current_pos = chosen[-1]

    return result


def total_travel_distance(polylines: List[Polyline]) -> float:
    """Calculates total rapid travel distance between strokes (mm)."""
    if len(polylines) < 2:
        return 0.0
    total = 0.0
    for i in range(len(polylines) - 1):
        total += _dist(polylines[i][-1], polylines[i + 1][0])
    return total


def total_draw_distance(polylines: List[Polyline]) -> float:
    """Calculates total linear drawing distance (mm)."""
    total = 0.0
    for pl in polylines:
        for i in range(len(pl) - 1):
            total += _dist(pl[i], pl[i + 1])
    return total


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
