"""Hybrid communication-aware trajectory planning for the LAESim use case.

The expert planner follows the primitive-generation and safe-set selection
structure described by Neural-Primitive. An optional radio-grid guide provides
global connectivity guarantees for the demonstrator. This module does not
implement or claim the paper's learned Npe2eNet policy.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

import numpy as np

from .runtime import PositionOutOfBoundsError, RadioMapLookup, RadioObservation

Vec3 = tuple[float, float, float]


class PlanningError(RuntimeError):
    """No valid primitive or complete route can be produced."""


@dataclass(frozen=True)
class PlannerConfig:
    primitive_duration_s: float = 2.0
    sample_period_s: float = 0.05
    execution_fraction: float = 2.0 / 3.0
    cruise_speed_mps: float = 8.0
    maximum_speed_mps: float = 15.0
    maximum_acceleration_mps2: float = 20.0
    heading_span_deg: float = 120.0
    heading_sample_count: int = 17
    vertical_offsets_m: tuple[float, ...] = (0.0,)
    uav_radius_m: float = 1.0
    target_tolerance_m: float = 3.0
    maximum_replans: int = 300
    minimum_progress_m: float = 0.05
    maximum_no_improvement_replans: int = 24
    target_weight: float = 1.0
    length_weight: float = 0.05
    radio_weight: float = 6.0
    handover_weight: float = 0.5
    minimum_sinr_db: float = 0.0
    minimum_serving_rss_dbm: float | None = None
    maximum_outage_fraction: float = 0.0
    enforce_connectivity: bool = True
    detection_threshold_dbm: float = -125.0
    global_guidance_enabled: bool = False
    global_guidance_margin_db: float = 0.0

    def validate(self) -> None:
        positive = {
            "primitive_duration_s": self.primitive_duration_s,
            "sample_period_s": self.sample_period_s,
            "cruise_speed_mps": self.cruise_speed_mps,
            "maximum_speed_mps": self.maximum_speed_mps,
            "maximum_acceleration_mps2": self.maximum_acceleration_mps2,
            "uav_radius_m": self.uav_radius_m,
            "target_tolerance_m": self.target_tolerance_m,
        }
        if any(not math.isfinite(value) or value <= 0.0 for value in positive.values()):
            raise ValueError(f"Planner values must be finite and positive: {positive}")
        if not 0.0 < self.execution_fraction <= 1.0:
            raise ValueError("execution_fraction must lie in (0, 1].")
        if self.heading_sample_count < 3 or self.heading_sample_count % 2 == 0:
            raise ValueError("heading_sample_count must be an odd integer of at least 3.")
        if self.maximum_replans < 1:
            raise ValueError("maximum_replans must be positive.")
        if self.maximum_no_improvement_replans < 1:
            raise ValueError("maximum_no_improvement_replans must be positive.")
        if not 0.0 <= self.maximum_outage_fraction <= 1.0:
            raise ValueError("maximum_outage_fraction must lie in [0, 1].")
        if not math.isfinite(self.global_guidance_margin_db) or self.global_guidance_margin_db < 0.0:
            raise ValueError("global_guidance_margin_db must be finite and non-negative.")


@dataclass(frozen=True)
class PrimitiveMetrics:
    target_cost_m: float
    length_m: float
    radio_cost: float
    outage_fraction: float
    minimum_sinr_db: float | None
    mean_sinr_db: float | None
    minimum_serving_rss_dbm: float | None
    mean_serving_rss_dbm: float | None
    handover_count: int
    total_cost: float


@dataclass(frozen=True)
class TrajectoryPrimitive:
    coefficients: np.ndarray
    duration_s: float
    sample_times_s: np.ndarray
    positions_m: np.ndarray
    velocities_mps: np.ndarray
    accelerations_mps2: np.ndarray
    serving_cells: tuple[str | None, ...]
    metrics: PrimitiveMetrics

    def state_at(self, time_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        time = min(max(float(time_s), 0.0), self.duration_s)
        position, velocity, acceleration = evaluate_quintic(self.coefficients, np.array([time]))
        return position[0], velocity[0], acceleration[0]


@dataclass(frozen=True)
class RouteMetrics:
    length_m: float
    outage_fraction: float
    minimum_sinr_db: float | None
    mean_sinr_db: float | None
    minimum_serving_rss_dbm: float | None
    mean_serving_rss_dbm: float | None
    handover_count: int
    replans: int
    final_error_m: float
    reached_goal: bool


@dataclass(frozen=True)
class PlannedRoute:
    mode: str
    start_m: Vec3
    goal_m: Vec3
    points_m: tuple[Vec3, ...]
    metrics: RouteMetrics
    planner_config: PlannerConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": "wireless-city-connectivity-aware-route-v1",
            "method": "neural-primitive-inspired-expert",
            "mode": self.mode,
            "start_m": list(self.start_m),
            "goal_m": list(self.goal_m),
            "points_m": [list(point) for point in self.points_m],
            "metrics": asdict(self.metrics),
            "planner_config": asdict(self.planner_config),
        }


def solve_minimum_jerk_quintic(
    start_position_m: np.ndarray,
    start_velocity_mps: np.ndarray,
    start_acceleration_mps2: np.ndarray,
    end_position_m: np.ndarray,
    end_velocity_mps: np.ndarray,
    end_acceleration_mps2: np.ndarray,
    duration_s: float,
) -> np.ndarray:
    """Return ascending fifth-order coefficients satisfying p/v/a boundaries."""
    duration = float(duration_s)
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError("duration_s must be finite and positive.")
    vectors = [
        np.asarray(value, dtype=float)
        for value in (
            start_position_m,
            start_velocity_mps,
            start_acceleration_mps2,
            end_position_m,
            end_velocity_mps,
            end_acceleration_mps2,
        )
    ]
    if any(value.shape != (3,) or not np.all(np.isfinite(value)) for value in vectors):
        raise ValueError("Trajectory boundary states must be finite three-vectors.")
    p0, v0, a0, p1, v1, a1 = vectors
    coefficients = np.zeros((6, 3), dtype=float)
    coefficients[0] = p0
    coefficients[1] = v0
    coefficients[2] = a0 / 2.0
    t = duration
    matrix = np.array(
        [
            [t**3, t**4, t**5],
            [3.0 * t**2, 4.0 * t**3, 5.0 * t**4],
            [6.0 * t, 12.0 * t**2, 20.0 * t**3],
        ],
        dtype=float,
    )
    known_position = coefficients[0] + coefficients[1] * t + coefficients[2] * t**2
    known_velocity = coefficients[1] + 2.0 * coefficients[2] * t
    known_acceleration = 2.0 * coefficients[2]
    rhs = np.vstack((p1 - known_position, v1 - known_velocity, a1 - known_acceleration))
    coefficients[3:6] = np.linalg.solve(matrix, rhs)
    return coefficients


def evaluate_quintic(
    coefficients: np.ndarray,
    times_s: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coeffs = np.asarray(coefficients, dtype=float)
    times = np.asarray(times_s, dtype=float)
    if coeffs.shape != (6, 3) or times.ndim != 1:
        raise ValueError("Expected coefficients with shape (6, 3) and one-dimensional times.")
    if not np.all(np.isfinite(coeffs)) or not np.all(np.isfinite(times)):
        raise ValueError("Trajectory coefficients and times must be finite.")
    position_basis = np.column_stack([times**order for order in range(6)])
    velocity_basis = np.column_stack(
        [np.zeros_like(times)] + [order * times ** (order - 1) for order in range(1, 6)]
    )
    acceleration_basis = np.column_stack(
        [np.zeros_like(times), np.zeros_like(times)]
        + [order * (order - 1) * times ** (order - 2) for order in range(2, 6)]
    )
    return position_basis @ coeffs, velocity_basis @ coeffs, acceleration_basis @ coeffs


class ConnectivityAwarePrimitivePlanner:
    def __init__(self, radio: RadioMapLookup, config: PlannerConfig | None = None) -> None:
        self.radio = radio
        self.scene = radio.scene
        self.config = config or PlannerConfig()
        self.config.validate()

    def plan(self, start_m: Vec3, goal_m: Vec3) -> PlannedRoute:
        start = _vector(start_m, "start_m")
        goal = _vector(goal_m, "goal_m")
        self._validate_endpoint(start, "start_m")
        self._validate_endpoint(goal, "goal_m")
        if self.config.global_guidance_enabled:
            if not self.config.enforce_connectivity:
                raise ValueError("Global radio guidance requires enforce_connectivity=True.")
            return self._plan_with_global_guide(start, goal)
        return self._plan_local(start, goal)

    def _plan_local(self, start: np.ndarray, goal: np.ndarray) -> PlannedRoute:
        current_position = start.copy()
        current_velocity = np.zeros(3, dtype=float)
        current_acceleration = np.zeros(3, dtype=float)
        route_points: list[Vec3] = [tuple(float(value) for value in current_position)]
        best_distance = float(np.linalg.norm(goal - current_position))
        last_improvement_replan = 0
        replan_count = 0
        for replan_index in range(self.config.maximum_replans):
            if np.linalg.norm(goal - current_position) <= self.config.target_tolerance_m:
                break
            primitive = self.select_primitive(
                current_position,
                current_velocity,
                current_acceleration,
                goal,
            )
            replan_count += 1
            execution_time = min(
                primitive.duration_s * self.config.execution_fraction,
                primitive.duration_s,
            )
            mask = (primitive.sample_times_s > 0.0) & (
                primitive.sample_times_s <= execution_time + 1e-9
            )
            executed = primitive.positions_m[mask]
            if len(executed) == 0:
                raise PlanningError("The selected primitive produced no executable samples.")
            next_position, next_velocity, next_acceleration = primitive.state_at(execution_time)
            if not np.allclose(executed[-1], next_position, atol=1e-9):
                executed = np.vstack((executed, next_position))
            distance_to_goal = float(np.linalg.norm(goal - next_position))
            if distance_to_goal < best_distance - self.config.minimum_progress_m:
                best_distance = distance_to_goal
                last_improvement_replan = replan_index + 1
            if (
                replan_index + 1 - last_improvement_replan
                >= self.config.maximum_no_improvement_replans
            ):
                raise PlanningError(
                    "Planner made no meaningful net progress for "
                    f"{self.config.maximum_no_improvement_replans} replans."
                )
            route_points.extend(tuple(float(value) for value in point) for point in executed)
            current_position = next_position
            current_velocity = next_velocity
            current_acceleration = next_acceleration
        else:
            raise PlanningError(
                f"Goal was not reached within {self.config.maximum_replans} replans."
            )
        if np.linalg.norm(goal - np.asarray(route_points[-1], dtype=float)) > 1e-6:
            direct = self._direct_goal_primitive(current_position, current_velocity, current_acceleration, goal)
            if direct is not None:
                route_points.extend(
                    tuple(float(value) for value in point)
                    for point in direct.positions_m[direct.sample_times_s > 0.0]
                )
        final_error = float(np.linalg.norm(goal - np.asarray(route_points[-1], dtype=float)))
        if final_error > self.config.target_tolerance_m:
            raise PlanningError(
                f"Planner did not reach the goal tolerance; final error={final_error:.3f} m."
            )
        metrics = self._route_metrics(route_points, replan_count, goal)
        mode = "connectivity-aware" if self.config.enforce_connectivity or self.config.radio_weight > 0.0 else "geometry-only"
        return PlannedRoute(
            mode=mode,
            start_m=tuple(float(value) for value in start),
            goal_m=tuple(float(value) for value in goal),
            points_m=tuple(route_points),
            metrics=metrics,
            planner_config=self.config,
        )

    def _plan_with_global_guide(self, start: np.ndarray, goal: np.ndarray) -> PlannedRoute:
        guide = self._global_guide(start, goal)
        points: list[Vec3] = [tuple(float(value) for value in start)]
        sample_spacing = max(0.5, self.config.cruise_speed_mps * self.config.sample_period_s)
        for first, second in pairwise(guide):
            length = float(np.linalg.norm(second - first))
            count = max(2, math.ceil(length / sample_spacing) + 1)
            points.extend(
                tuple(float(value) for value in point)
                for point in np.linspace(first, second, count)[1:]
            )
        replans = len(guide) - 1
        metrics = self._route_metrics(points, replans, goal)
        if metrics.outage_fraction > self.config.maximum_outage_fraction + 1e-12:
            raise PlanningError(
                "The smoothed globally guided route violates the configured connectivity constraint; "
                f"outage_fraction={metrics.outage_fraction:.6f}, "
                f"minimum_sinr_db={metrics.minimum_sinr_db}."
            )
        return PlannedRoute(
            mode="connectivity-aware",
            start_m=tuple(float(value) for value in start),
            goal_m=tuple(float(value) for value in goal),
            points_m=tuple(points),
            metrics=metrics,
            planner_config=self.config,
        )

    def _global_guide(self, start: np.ndarray, goal: np.ndarray) -> list[np.ndarray]:
        x_axis = np.asarray(self.radio.x_m, dtype=float)
        y_axis = np.asarray(self.radio.y_m, dtype=float)
        if len(x_axis) < 2 or len(y_axis) < 2:
            raise PlanningError("Global guidance requires at least a 2 x 2 radio grid.")
        altitude = float(start[2])
        if abs(float(goal[2]) - altitude) > 1e-6:
            raise PlanningError("Global radio guidance currently requires a constant flight altitude.")

        observations: dict[tuple[int, int], RadioObservation] = {}

        def point(node: tuple[int, int]) -> np.ndarray:
            yi, xi = node
            return np.array([x_axis[xi], y_axis[yi], altitude], dtype=float)

        def observation(node: tuple[int, int]) -> RadioObservation:
            if node not in observations:
                observations[node] = self.radio.query(
                    tuple(float(value) for value in point(node)),
                    detection_threshold_dbm=self.config.detection_threshold_dbm,
                    outage_threshold_db=self.config.minimum_sinr_db,
                )
            return observations[node]

        def node_feasible(node: tuple[int, int]) -> bool:
            candidate = point(node)
            if not self._collision_free(np.asarray([candidate])):
                return False
            return self._observation_feasible(
                observation(node),
                sinr_margin_db=self.config.global_guidance_margin_db,
            )

        all_nodes = [
            (yi, xi)
            for yi in range(len(y_axis))
            for xi in range(len(x_axis))
            if node_feasible((yi, xi))
        ]
        if not all_nodes:
            raise PlanningError("No feasible cells exist in the configured radio grid.")

        def endpoint_node(endpoint: np.ndarray) -> tuple[int, int]:
            ordered = sorted(all_nodes, key=lambda node: float(np.linalg.norm(point(node) - endpoint)))
            for node in ordered:
                if self._segment_feasible(
                    endpoint,
                    point(node),
                    sinr_margin_db=self.config.global_guidance_margin_db,
                ):
                    return node
            raise PlanningError("An endpoint cannot connect to the feasible radio grid.")

        start_node = endpoint_node(start)
        goal_node = endpoint_node(goal)
        queue: list[tuple[float, tuple[int, int]]] = [(0.0, start_node)]
        costs = {start_node: 0.0}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        visited: set[tuple[int, int]] = set()
        neighbour_offsets = (
            (-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1),
        )
        while queue:
            _, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current == goal_node:
                break
            cy, cx = current
            for dy, dx in neighbour_offsets:
                neighbour = (cy + dy, cx + dx)
                if not (0 <= neighbour[0] < len(y_axis) and 0 <= neighbour[1] < len(x_axis)):
                    continue
                if not node_feasible(neighbour) or not self._segment_feasible(
                    point(current),
                    point(neighbour),
                    sinr_margin_db=self.config.global_guidance_margin_db,
                ):
                    continue
                edge_length = float(np.linalg.norm(point(neighbour) - point(current)))
                sinr = observation(neighbour).sinr_db
                preferred = self.config.minimum_sinr_db + self.config.global_guidance_margin_db
                deficit = max(0.0, preferred - float(sinr)) / max(self.config.global_guidance_margin_db, 1.0)
                candidate_cost = costs[current] + edge_length * (1.0 + self.config.radio_weight * deficit**2)
                if candidate_cost >= costs.get(neighbour, math.inf):
                    continue
                costs[neighbour] = candidate_cost
                parents[neighbour] = current
                heuristic = float(np.linalg.norm(point(neighbour)[:2] - point(goal_node)[:2]))
                heapq.heappush(queue, (candidate_cost + heuristic, neighbour))
        if goal_node not in costs:
            raise PlanningError("No globally connected route exists at the configured thresholds.")

        node_path = [goal_node]
        while node_path[-1] != start_node:
            node_path.append(parents[node_path[-1]])
        raw = [start, *(point(node) for node in reversed(node_path)), goal]
        deduplicated = [raw[0]]
        for candidate in raw[1:]:
            if not np.allclose(candidate, deduplicated[-1]):
                deduplicated.append(candidate)
        simplified = [deduplicated[0]]
        index = 0
        while index < len(deduplicated) - 1:
            next_index = len(deduplicated) - 1
            while next_index > index + 1 and not self._segment_feasible(
                deduplicated[index],
                deduplicated[next_index],
                sinr_margin_db=self.config.global_guidance_margin_db,
            ):
                next_index -= 1
            simplified.append(deduplicated[next_index])
            index = next_index
        return simplified

    def _segment_feasible(
        self,
        start: np.ndarray,
        end: np.ndarray,
        *,
        sinr_margin_db: float = 0.0,
    ) -> bool:
        length = float(np.linalg.norm(end - start))
        x_spacing = float(np.min(np.diff(np.asarray(self.radio.x_m, dtype=float))))
        y_spacing = float(np.min(np.diff(np.asarray(self.radio.y_m, dtype=float))))
        route_sample_spacing = max(
            0.5,
            self.config.cruise_speed_mps * self.config.sample_period_s,
        )
        spacing = min(
            max(0.5, min(x_spacing, y_spacing) / 40.0),
            route_sample_spacing,
        )
        count = max(2, math.ceil(length / spacing) + 1)
        points = np.linspace(start, end, count)
        if not self._collision_free(points):
            return False
        try:
            return all(
                self._observation_feasible(
                    self.radio.query(
                        tuple(float(value) for value in candidate),
                        detection_threshold_dbm=self.config.detection_threshold_dbm,
                        outage_threshold_db=self.config.minimum_sinr_db,
                    ),
                    sinr_margin_db=sinr_margin_db,
                )
                for candidate in points
            )
        except PositionOutOfBoundsError:
            return False

    def _observation_feasible(
        self,
        observation: RadioObservation,
        *,
        sinr_margin_db: float = 0.0,
    ) -> bool:
        if (
            observation.outage
            or observation.sinr_db is None
            or observation.sinr_db < self.config.minimum_sinr_db + sinr_margin_db
        ):
            return False
        if self.config.minimum_serving_rss_dbm is None:
            return True
        serving_rss = (
            observation.rss_dbm.get(observation.serving_cell)
            if observation.serving_cell is not None
            else None
        )
        return serving_rss is not None and serving_rss >= self.config.minimum_serving_rss_dbm

    def select_primitive(
        self,
        position_m: np.ndarray,
        velocity_mps: np.ndarray,
        acceleration_mps2: np.ndarray,
        goal_m: np.ndarray,
    ) -> TrajectoryPrimitive:
        candidates = self.generate_primitives(position_m, velocity_mps, acceleration_mps2, goal_m)
        if not candidates:
            raise PlanningError("No collision-free, dynamically feasible primitive satisfies the configured constraints.")
        return min(candidates, key=lambda primitive: primitive.metrics.total_cost)

    def generate_primitives(
        self,
        position_m: np.ndarray,
        velocity_mps: np.ndarray,
        acceleration_mps2: np.ndarray,
        goal_m: np.ndarray,
    ) -> list[TrajectoryPrimitive]:
        position = _vector(position_m, "position_m")
        velocity = _vector(velocity_mps, "velocity_mps")
        acceleration = _vector(acceleration_mps2, "acceleration_mps2")
        goal = _vector(goal_m, "goal_m")
        delta = goal - position
        horizontal_distance = float(np.linalg.norm(delta[:2]))
        if horizontal_distance <= 1e-9:
            base_angle = math.atan2(float(velocity[1]), float(velocity[0])) if np.linalg.norm(velocity[:2]) > 0.1 else 0.0
        elif np.linalg.norm(velocity[:2]) > 0.5:
            base_angle = math.atan2(float(velocity[1]), float(velocity[0]))
        else:
            base_angle = math.atan2(float(delta[1]), float(delta[0]))
        heading_offsets = np.linspace(
            -self.config.heading_span_deg,
            self.config.heading_span_deg,
            self.config.heading_sample_count,
        )
        travel_distance = self.config.cruise_speed_mps * self.config.primitive_duration_s
        endpoints: list[tuple[np.ndarray, np.ndarray]] = []
        for offset_deg in heading_offsets:
            angle = base_angle + math.radians(float(offset_deg))
            direction = np.array([math.cos(angle), math.sin(angle), 0.0], dtype=float)
            for vertical_offset in self.config.vertical_offsets_m:
                endpoint = position + direction * travel_distance
                endpoint[2] = position[2] + float(vertical_offset)
                end_velocity = direction * self.config.cruise_speed_mps
                endpoints.append((endpoint, end_velocity))
        if float(np.linalg.norm(delta)) <= travel_distance * 1.25:
            goal_direction = delta / max(float(np.linalg.norm(delta)), 1e-9)
            endpoints.append((goal.copy(), goal_direction * min(self.config.cruise_speed_mps, float(np.linalg.norm(delta)))))
        candidates: list[TrajectoryPrimitive] = []
        for endpoint, end_velocity in endpoints:
            primitive = self._candidate(position, velocity, acceleration, endpoint, end_velocity, goal)
            if primitive is not None:
                candidates.append(primitive)
        return candidates

    def _direct_goal_primitive(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        acceleration: np.ndarray,
        goal: np.ndarray,
    ) -> TrajectoryPrimitive | None:
        return self._candidate(
            position,
            velocity,
            acceleration,
            goal,
            np.zeros(3, dtype=float),
            goal,
            duration_s=self.config.primitive_duration_s,
        )

    def _candidate(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        acceleration: np.ndarray,
        endpoint: np.ndarray,
        end_velocity: np.ndarray,
        goal: np.ndarray,
        *,
        duration_s: float | None = None,
    ) -> TrajectoryPrimitive | None:
        duration = float(duration_s or self.config.primitive_duration_s)
        coefficients = solve_minimum_jerk_quintic(
            position,
            velocity,
            acceleration,
            endpoint,
            end_velocity,
            np.zeros(3, dtype=float),
            duration,
        )
        sample_count = max(2, math.ceil(duration / self.config.sample_period_s) + 1)
        times = np.linspace(0.0, duration, sample_count)
        positions, velocities, accelerations = evaluate_quintic(coefficients, times)
        if np.max(np.linalg.norm(velocities, axis=1)) > self.config.maximum_speed_mps + 1e-7:
            return None
        if np.max(np.linalg.norm(accelerations, axis=1)) > self.config.maximum_acceleration_mps2 + 1e-7:
            return None
        if not self._collision_free(positions):
            return None
        observations: list[RadioObservation] = []
        try:
            for point in positions:
                observations.append(
                    self.radio.query(
                        tuple(float(value) for value in point),
                        detection_threshold_dbm=self.config.detection_threshold_dbm,
                        outage_threshold_db=self.config.minimum_sinr_db,
                    )
                )
        except PositionOutOfBoundsError:
            return None
        metrics, serving_cells = self._primitive_metrics(positions, goal, observations)
        if self.config.enforce_connectivity and metrics.outage_fraction > self.config.maximum_outage_fraction + 1e-12:
            return None
        return TrajectoryPrimitive(
            coefficients=coefficients,
            duration_s=duration,
            sample_times_s=times,
            positions_m=positions,
            velocities_mps=velocities,
            accelerations_mps2=accelerations,
            serving_cells=serving_cells,
            metrics=metrics,
        )

    def _primitive_metrics(
        self,
        positions: np.ndarray,
        goal: np.ndarray,
        observations: list[RadioObservation],
    ) -> tuple[PrimitiveMetrics, tuple[str | None, ...]]:
        distances = np.linalg.norm(positions - goal, axis=1)
        primitive_length = _path_length(positions)
        initial_target_distance = float(np.linalg.norm(positions[0] - goal))
        target_cost = float(distances[-1] if initial_target_distance > primitive_length else np.min(distances))
        radio = _radio_statistics(
            observations,
            minimum_sinr_db=self.config.minimum_sinr_db,
            minimum_serving_rss_dbm=self.config.minimum_serving_rss_dbm,
        )
        total_cost = (
            self.config.target_weight * target_cost
            + self.config.length_weight * primitive_length
            + self.config.radio_weight * float(radio["radio_cost"])
            + self.config.handover_weight * int(radio["handover_count"])
        )
        metrics = PrimitiveMetrics(
            target_cost_m=target_cost,
            length_m=primitive_length,
            radio_cost=float(radio["radio_cost"]),
            outage_fraction=float(radio["outage_fraction"]),
            minimum_sinr_db=radio["minimum_sinr_db"],
            mean_sinr_db=radio["mean_sinr_db"],
            minimum_serving_rss_dbm=radio["minimum_serving_rss_dbm"],
            mean_serving_rss_dbm=radio["mean_serving_rss_dbm"],
            handover_count=int(radio["handover_count"]),
            total_cost=float(total_cost),
        )
        return metrics, tuple(radio["serving_cells"])

    def _route_metrics(self, points: list[Vec3], replans: int, goal: np.ndarray) -> RouteMetrics:
        array = np.asarray(points, dtype=float)
        observations = [
            self.radio.query(
                point,
                detection_threshold_dbm=self.config.detection_threshold_dbm,
                outage_threshold_db=self.config.minimum_sinr_db,
            )
            for point in points
        ]
        radio = _radio_statistics(
            observations,
            minimum_sinr_db=self.config.minimum_sinr_db,
            minimum_serving_rss_dbm=self.config.minimum_serving_rss_dbm,
        )
        final_error = float(np.linalg.norm(array[-1] - goal))
        return RouteMetrics(
            length_m=_path_length(array),
            outage_fraction=float(radio["outage_fraction"]),
            minimum_sinr_db=radio["minimum_sinr_db"],
            mean_sinr_db=radio["mean_sinr_db"],
            minimum_serving_rss_dbm=radio["minimum_serving_rss_dbm"],
            mean_serving_rss_dbm=radio["mean_serving_rss_dbm"],
            handover_count=int(radio["handover_count"]),
            replans=replans,
            final_error_m=final_error,
            reached_goal=final_error <= self.config.target_tolerance_m,
        )

    def _collision_free(self, positions: np.ndarray) -> bool:
        radius = self.config.uav_radius_m
        lower = np.asarray(self.scene.bounds_min_m, dtype=float)
        upper = np.asarray(self.scene.bounds_max_m, dtype=float)
        if np.any(positions < lower) or np.any(positions > upper):
            return False
        for building in self.scene.buildings:
            center = np.asarray(building["center_m"], dtype=float)
            half_size = np.asarray(building["size_m"], dtype=float) / 2.0 + radius
            if np.any(np.all(np.abs(positions - center) <= half_size, axis=1)):
                return False
        return True

    def _validate_endpoint(self, point: np.ndarray, name: str) -> None:
        lower = np.asarray(self.scene.bounds_min_m, dtype=float)
        upper = np.asarray(self.scene.bounds_max_m, dtype=float)
        if np.any(point < lower) or np.any(point > upper):
            raise ValueError(f"{name} lies outside scene bounds.")
        if not self._collision_free(np.asarray([point], dtype=float)):
            raise ValueError(f"{name} is not collision-free with the configured UAV radius.")
        if point[2] < float(self.radio.z_m[0]) or point[2] > float(self.radio.z_m[-1]):
            raise ValueError(f"{name} lies outside the radio-map altitude range.")


def _radio_statistics(
    observations: list[RadioObservation],
    *,
    minimum_sinr_db: float,
    minimum_serving_rss_dbm: float | None,
) -> dict[str, Any]:
    if not observations:
        raise ValueError("At least one radio observation is required.")
    sinr_values: list[float] = []
    rss_values: list[float] = []
    serving_cells: list[str | None] = []
    outages: list[bool] = []
    deficits: list[float] = []
    for observation in observations:
        serving_cells.append(observation.serving_cell)
        serving_rss = (
            observation.rss_dbm.get(observation.serving_cell)
            if observation.serving_cell is not None
            else None
        )
        sinr = observation.sinr_db
        outage = observation.outage or sinr is None
        deficit = 0.0
        if sinr is None:
            deficit += 4.0
        else:
            sinr_values.append(float(sinr))
            deficit += (max(0.0, minimum_sinr_db - float(sinr)) / 10.0) ** 2
        if serving_rss is None:
            outage = True
            if minimum_serving_rss_dbm is not None:
                deficit += 4.0
        else:
            rss_values.append(float(serving_rss))
            if minimum_serving_rss_dbm is not None:
                rss_deficit = max(0.0, minimum_serving_rss_dbm - float(serving_rss))
                deficit += (rss_deficit / 10.0) ** 2
                outage = outage or serving_rss < minimum_serving_rss_dbm
        outages.append(outage)
        deficits.append(deficit)
    handovers = sum(
        first is not None and second is not None and first != second
        for first, second in pairwise(serving_cells)
    )
    return {
        "radio_cost": float(np.mean(deficits)),
        "outage_fraction": float(np.mean(outages)),
        "minimum_sinr_db": min(sinr_values) if sinr_values else None,
        "mean_sinr_db": float(np.mean(sinr_values)) if sinr_values else None,
        "minimum_serving_rss_dbm": min(rss_values) if rss_values else None,
        "mean_serving_rss_dbm": float(np.mean(rss_values)) if rss_values else None,
        "handover_count": handovers,
        "serving_cells": serving_cells,
    }


def _path_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


def _vector(value: Any, name: str) -> np.ndarray:
    vector = np.asarray(value, dtype=float)
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must contain three finite values.")
    return vector.copy()
