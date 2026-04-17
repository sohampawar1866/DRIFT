"""Unit tests for backend/mission/tsp.py (D-11 greedy + 2-opt).

Tests:
- Test 1: greedy_nearest_neighbor on 4 collinear points east of origin returns
  monotonic east ordering [0, 1, 2, 3].
- Test 2: two_opt on a known suboptimal (crossing) tour reduces total distance.
- Test 3: tour_distance_km on closed tour equals sum of haversine legs.
- Test 4: two_opt on already-optimal tour returns same order (no improving swap).
- Test 5: two_opt respects iteration cap via max_iters.
"""
from __future__ import annotations

import random

import pytest

from backend.mission.scoring import haversine_km
from backend.mission.tsp import (
    greedy_nearest_neighbor,
    tour_distance_km,
    two_opt,
)


def test_greedy_monotonic_east() -> None:
    origin = (72.8, 18.9)
    # Four points marching due east from origin.
    points = [(72.9, 18.9), (73.0, 18.9), (73.1, 18.9), (73.2, 18.9)]
    order = greedy_nearest_neighbor(origin, points)
    assert order == [0, 1, 2, 3]


def test_two_opt_improves_suboptimal_tour() -> None:
    """Square corners visited in crossing order -> 2-opt should uncross."""
    origin = (0.0, 0.0)
    # Unit-ish square around origin (in degrees; haversine is monotonic so OK).
    points = [
        (1.0, 0.0),  # E
        (0.0, 1.0),  # N
        (1.0, 1.0),  # NE
        (0.0, 0.0001),  # near origin (tiny offset to differ)
    ]
    # Intentionally crossing order: E -> NE -> near-origin -> N
    bad_order = [0, 2, 3, 1]
    bad_d = tour_distance_km(origin, points, bad_order)
    improved = two_opt(origin, points, bad_order)
    improved_d = tour_distance_km(origin, points, improved)
    assert improved_d <= bad_d
    # On this non-degenerate crossing, improvement must be strict.
    assert improved_d < bad_d


def test_tour_distance_km_closed() -> None:
    origin = (72.8, 18.9)
    points = [(72.9, 18.9), (73.0, 19.0)]
    order = [0, 1]
    expected = (
        haversine_km(origin, points[0])
        + haversine_km(points[0], points[1])
        + haversine_km(points[1], origin)
    )
    got = tour_distance_km(origin, points, order)
    assert got == pytest.approx(expected, abs=0.01)


def test_two_opt_optimal_tour_unchanged() -> None:
    origin = (0.0, 0.0)
    # Already-optimal monotonic east-then-back ordering.
    points = [(1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    order = [0, 1, 2]
    result = two_opt(origin, points, order)
    # Result should be the same tour (no improving swap).
    assert result == order


def test_two_opt_respects_iteration_cap() -> None:
    """Feed 50 random points and assert termination under O(N^2) cap."""
    rng = random.Random(0)
    origin = (0.0, 0.0)
    points = [(rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0)) for _ in range(50)]
    order = list(range(len(points)))
    # Explicit small cap -> must return without hanging.
    result = two_opt(origin, points, order, max_iters=100)
    assert len(result) == len(order)
    assert sorted(result) == sorted(order)  # permutation preserved
