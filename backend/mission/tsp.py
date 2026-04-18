"""TSP primitives: greedy nearest-neighbor + 2-opt improvement.

All distances are great-circle (haversine) in km. 'Points' are (lon, lat)
tuples. Tours are represented as ordered lists of point indices into a
candidates array; the origin is prepended/appended at the route-building
layer, NOT here.

Implements greedy construction followed by 2-opt until convergence
(or an N**2 iteration cap, whichever comes first).
"""
from __future__ import annotations

from typing import Sequence

from backend.mission.scoring import haversine_km

__all__ = ["tour_distance_km", "greedy_nearest_neighbor", "two_opt"]


def tour_distance_km(
    origin: tuple[float, float],
    points: Sequence[tuple[float, float]],
    order: Sequence[int],
) -> float:
    """Closed-tour distance: origin -> points[order[0]] -> ... -> origin.

    Empty order -> 0.0.
    """
    if not order:
        return 0.0
    total = haversine_km(origin, points[order[0]])
    for i in range(len(order) - 1):
        total += haversine_km(points[order[i]], points[order[i + 1]])
    total += haversine_km(points[order[-1]], origin)
    return total


def greedy_nearest_neighbor(
    origin: tuple[float, float],
    points: Sequence[tuple[float, float]],
) -> list[int]:
    """Start at origin, always move to the nearest unvisited point.

    Returns permutation of indices into `points`. Empty input -> [].
    """
    if not points:
        return []
    remaining = set(range(len(points)))
    current = origin
    order: list[int] = []
    while remaining:
        nxt = min(remaining, key=lambda i: haversine_km(current, points[i]))
        order.append(nxt)
        remaining.remove(nxt)
        current = points[nxt]
    return order


def two_opt(
    origin: tuple[float, float],
    points: Sequence[tuple[float, float]],
    order: list[int],
    max_iters: int | None = None,
) -> list[int]:
    """2-opt improvement: reverse sub-tours while distance strictly decreases.

    Terminates when no improving swap exists OR `max_iters` swap-evaluations
    have been performed (default N**2 safety cap).

    Args:
        origin: (lon, lat) vessel start/end.
        points: sequence of (lon, lat) waypoint coordinates.
        order: initial tour as list of indices into `points`.
        max_iters: optional upper bound on swap evaluations; defaults to N**2.

    Returns:
        Possibly-improved order (same multiset of indices as input).
    """
    n = len(order)
    if n < 4:
        # 2-opt on fewer than 4 stops cannot improve a closed tour meaningfully.
        return list(order)
    cap = max_iters if max_iters is not None else n * n
    order = list(order)
    best_d = tour_distance_km(origin, points, order)
    improved = True
    iters = 0
    while improved and iters < cap:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    # Adjacent edges share a node; reversing a 2-slice is a no-op.
                    continue
                iters += 1
                new_order = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                new_d = tour_distance_km(origin, points, new_order)
                if new_d + 1e-9 < best_d:
                    order = new_order
                    best_d = new_d
                    improved = True
                if iters >= cap:
                    break
            if iters >= cap:
                break
    return order
