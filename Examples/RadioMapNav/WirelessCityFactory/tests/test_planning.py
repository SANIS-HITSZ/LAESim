import json

import numpy as np
import pytest

from wireless_city_factory.planning import (
    ConnectivityAwarePrimitivePlanner,
    PlannerConfig,
    PlanningError,
    evaluate_quintic,
    solve_minimum_jerk_quintic,
)
from wireless_city_factory.runtime import PositionOutOfBoundsError, RadioObservation
from wireless_city_factory.schema import Scene


def _scene(*, buildings=None) -> Scene:
    return Scene(
        schema_version="wireless-city-scene",
        scene_id="planner-test",
        seed=1,
        units="m",
        frame="right-handed,+z-up",
        bounds_min_m=(0.0, 0.0, 0.0),
        bounds_max_m=(100.0, 100.0, 100.0),
        roads=[],
        blocks=[],
        buildings=list(buildings or []),
        base_stations=[],
        tasks=[{"task_id": "task-000", "start_m": [10.0, 50.0, 50.0], "goal_m": [90.0, 50.0, 50.0]}],
    )


class FakeRadio:
    def __init__(self, scene: Scene, *, weak_strip: bool = False) -> None:
        self.scene = scene
        self.x_m = np.linspace(0.0, 100.0, 21)
        self.y_m = np.linspace(0.0, 100.0, 21)
        self.z_m = np.array([0.0, 100.0])
        self.weak_strip = weak_strip

    def query(self, position, *, detection_threshold_dbm=-125.0, outage_threshold_db=-6.0):
        x, y, z = (float(value) for value in position)
        if not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0 and 0.0 <= z <= 100.0):
            raise PositionOutOfBoundsError("outside test map")
        weak = self.weak_strip and 14.0 < x < 75.0 and abs(y - 50.0) < 1.5
        sinr = -12.0 if weak else 12.0
        rss = -112.0 if weak else -72.0
        cell = "cell-a"
        return RadioObservation(
            position_m=(x, y, z),
            interpolation="fake",
            detected_cells=[{"cell_id": cell}],
            rss_dbm={cell: rss},
            serving_cell=cell,
            sinr_db=sinr,
            outage=sinr < outage_threshold_db,
            detection_threshold_dbm=detection_threshold_dbm,
            outage_threshold_db=outage_threshold_db,
        )


def _config(**overrides) -> PlannerConfig:
    values = {
        "primitive_duration_s": 2.0,
        "sample_period_s": 0.05,
        "execution_fraction": 1.0,
        "cruise_speed_mps": 10.0,
        "maximum_speed_mps": 30.0,
        "maximum_acceleration_mps2": 50.0,
        "heading_span_deg": 60.0,
        "heading_sample_count": 3,
        "uav_radius_m": 0.5,
        "target_tolerance_m": 1.0,
        "radio_weight": 0.0,
        "handover_weight": 0.0,
        "enforce_connectivity": False,
    }
    values.update(overrides)
    return PlannerConfig(**values)


def test_quintic_satisfies_both_boundary_states() -> None:
    p0 = np.array([1.0, 2.0, 3.0])
    v0 = np.array([0.5, -0.2, 0.1])
    a0 = np.array([0.1, 0.2, -0.1])
    p1 = np.array([8.0, 5.0, 4.0])
    v1 = np.array([1.0, 0.0, -0.5])
    a1 = np.array([0.0, -0.1, 0.2])
    coefficients = solve_minimum_jerk_quintic(p0, v0, a0, p1, v1, a1, 2.0)
    position, velocity, acceleration = evaluate_quintic(coefficients, np.array([0.0, 2.0]))
    assert position == pytest.approx(np.vstack((p0, p1)))
    assert velocity == pytest.approx(np.vstack((v0, v1)))
    assert acceleration == pytest.approx(np.vstack((a0, a1)))


def test_collision_and_out_of_bounds_candidates_are_rejected() -> None:
    building = {
        "building_id": "building-000",
        "block_id": "block-000",
        "center_m": [20.0, 50.0, 50.0],
        "size_m": [6.0, 12.0, 100.0],
    }
    planner = ConnectivityAwarePrimitivePlanner(FakeRadio(_scene(buildings=[building])), _config())
    start = np.array([10.0, 50.0, 50.0])
    zero = np.zeros(3)
    goal = np.array([90.0, 50.0, 50.0])
    assert planner._candidate(start, zero, zero, np.array([30.0, 50.0, 50.0]), zero, goal) is None
    assert planner._candidate(start, zero, zero, np.array([-5.0, 50.0, 50.0]), zero, goal) is None


def test_hard_connectivity_rejects_weak_straight_primitive() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene(), weak_strip=True),
        _config(enforce_connectivity=True, maximum_outage_fraction=0.0),
    )
    start = np.array([10.0, 50.0, 50.0])
    zero = np.zeros(3)
    goal = np.array([90.0, 50.0, 50.0])
    straight = planner._candidate(start, zero, zero, np.array([30.0, 50.0, 50.0]), zero, goal)
    assert straight is None


def test_default_dynamic_limits_allow_the_default_primitive() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene()),
        PlannerConfig(enforce_connectivity=False, radio_weight=0.0),
    )
    candidates = planner.generate_primitives(
        np.array([10.0, 50.0, 50.0]),
        np.zeros(3),
        np.zeros(3),
        np.array([90.0, 50.0, 50.0]),
    )
    assert candidates


def test_connectivity_cost_selects_longer_connected_primitive() -> None:
    radio = FakeRadio(_scene(), weak_strip=True)
    start = np.array([10.0, 50.0, 50.0])
    zero = np.zeros(3)
    goal = np.array([90.0, 50.0, 50.0])
    baseline = ConnectivityAwarePrimitivePlanner(radio, _config()).select_primitive(start, zero, zero, goal)
    connected = ConnectivityAwarePrimitivePlanner(
        radio,
        _config(radio_weight=100.0, enforce_connectivity=False),
    ).select_primitive(start, zero, zero, goal)
    assert abs(float(baseline.positions_m[-1, 1]) - 50.0) < 1e-6
    assert abs(float(connected.positions_m[-1, 1]) - 50.0) > 5.0
    assert connected.metrics.outage_fraction < baseline.metrics.outage_fraction


def test_global_radio_guide_routes_around_a_weak_strip() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene(), weak_strip=True),
        _config(
            global_guidance_enabled=True,
            enforce_connectivity=True,
            minimum_sinr_db=-6.0,
            maximum_outage_fraction=0.0,
        ),
    )
    route = planner.plan((10.0, 50.0, 50.0), (90.0, 50.0, 50.0))
    points = np.asarray(route.points_m)
    assert np.max(np.abs(points[:, 1] - 50.0)) > 1.5
    assert route.metrics.outage_fraction == pytest.approx(0.0)
    assert route.metrics.minimum_sinr_db == pytest.approx(12.0)


def test_segment_validation_uses_at_least_the_final_route_sampling_resolution() -> None:
    class NarrowWeakRadio(FakeRadio):
        def __init__(self, scene: Scene) -> None:
            super().__init__(scene)
            self.x_m = np.array([0.0, 40.0])
            self.y_m = np.array([0.0, 40.0])

        def query(self, position, *, detection_threshold_dbm=-125.0, outage_threshold_db=-6.0):
            observation = super().query(
                position,
                detection_threshold_dbm=detection_threshold_dbm,
                outage_threshold_db=outage_threshold_db,
            )
            if 0.4 < float(position[0]) < 0.6:
                return RadioObservation(
                    position_m=observation.position_m,
                    interpolation=observation.interpolation,
                    detected_cells=observation.detected_cells,
                    rss_dbm={"cell-a": -112.0},
                    serving_cell="cell-a",
                    sinr_db=-12.0,
                    outage=True,
                    detection_threshold_dbm=detection_threshold_dbm,
                    outage_threshold_db=outage_threshold_db,
                )
            return observation

    planner = ConnectivityAwarePrimitivePlanner(
        NarrowWeakRadio(_scene()),
        _config(
            global_guidance_enabled=True,
            enforce_connectivity=True,
            maximum_outage_fraction=0.0,
        ),
    )

    assert not planner._segment_feasible(
        np.array([0.0, 0.0, 50.0]),
        np.array([2.0, 0.0, 50.0]),
    )


def test_route_is_finite_serializable_and_reaches_goal() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene()),
        _config(target_tolerance_m=3.0, maximum_replans=20),
    )
    route = planner.plan((10.0, 50.0, 50.0), (42.0, 50.0, 50.0))
    payload = route.to_dict()
    assert np.all(np.isfinite(np.asarray(route.points_m)))
    assert route.points_m[-1] == pytest.approx((42.0, 50.0, 50.0))
    assert route.metrics.reached_goal is True
    assert route.metrics.final_error_m == pytest.approx(0.0)
    assert json.loads(json.dumps(payload, allow_nan=False))["contract"].endswith("route-v1")


def test_route_does_not_silently_succeed_before_goal() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene()),
        _config(maximum_replans=1, target_tolerance_m=0.1),
    )
    with pytest.raises(PlanningError, match="not reached"):
        planner.plan((10.0, 50.0, 50.0), (90.0, 50.0, 50.0))


def test_route_accepts_a_safe_endpoint_inside_the_configured_goal_tolerance() -> None:
    planner = ConnectivityAwarePrimitivePlanner(
        FakeRadio(_scene()),
        _config(target_tolerance_m=3.0),
    )
    planner._direct_goal_primitive = lambda *args: None
    route = planner.plan((10.0, 50.0, 50.0), (12.5, 50.0, 50.0))
    assert route.points_m[-1] == pytest.approx((10.0, 50.0, 50.0))
    assert route.metrics.final_error_m == pytest.approx(2.5)
    assert route.metrics.reached_goal is True
