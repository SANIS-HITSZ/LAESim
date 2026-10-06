"""Small, testable RPC bridge between generated routes and LAESim/AirSim."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from laesim_scene.repository import load_laesim_client

from .runtime import RadioMapLookup


@dataclass(frozen=True)
class LAESimState:
    timestamp_ns: int
    position_ned_m: tuple[float, float, float]
    position_scene_m: tuple[float, float, float]
    velocity_ned_mps: tuple[float, float, float]
    has_collided: bool
    collision_object: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LAESimBridge:
    """Use the AirSim-compatible API exposed by LAESim without importing it eagerly."""

    def __init__(
        self,
        lookup: RadioMapLookup,
        *,
        host: str = "127.0.0.1",
        port: int = 41471,
        vehicle_name: str = "UAV",
        task_id: str | None = None,
        airsim_module: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.lookup = lookup
        self.host = host
        self.port = int(port)
        self.vehicle_name = vehicle_name
        self.task_id = task_id
        self._airsim = airsim_module
        self._client = client
        self._connected = False

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("LAESim is not connected. Call connect() first.")
        return self._client

    def connect(self) -> None:
        if self._airsim is None:
            try:
                self._airsim = load_laesim_client()
            except ImportError as exc:
                raise RuntimeError(
                    "The AirSim Python package is required only for a live LAESim mission."
                ) from exc
        if self._client is None:
            self._client = self._airsim.MultirotorClient(ip=self.host, port=self.port)
        self.client.confirmConnection()
        self.client.enableApiControl(True, vehicle_name=self.vehicle_name)
        self._connected = True

    def prepare_flight(self, altitude_scene_m: float, *, vertical_speed_mps: float = 5.0) -> None:
        if vertical_speed_mps <= 0.0:
            raise ValueError("vertical_speed_mps must be positive.")
        task = self._task()
        target = (float(task["start_m"][0]), float(task["start_m"][1]), float(altitude_scene_m))
        target_ned_z = self.lookup.airsim_ned_from_canonical(target, task_id=self.task_id)[2]
        self.client.armDisarm(True, vehicle_name=self.vehicle_name)
        self.client.takeoffAsync(vehicle_name=self.vehicle_name).join()
        self.client.moveToZAsync(
            target_ned_z,
            vertical_speed_mps,
            vehicle_name=self.vehicle_name,
        ).join()
        self.client.hoverAsync(vehicle_name=self.vehicle_name).join()

    def read_state(self) -> LAESimState:
        state = self.client.getMultirotorState(vehicle_name=self.vehicle_name)
        position = _xyz(state.kinematics_estimated.position)
        velocity = _xyz(state.kinematics_estimated.linear_velocity)
        collision = self.client.simGetCollisionInfo(vehicle_name=self.vehicle_name)
        return LAESimState(
            timestamp_ns=int(state.timestamp),
            position_ned_m=position,
            position_scene_m=self.lookup.canonical_from_airsim_ned(position, task_id=self.task_id),
            velocity_ned_mps=velocity,
            has_collided=bool(collision.has_collided),
            collision_object=str(collision.object_name),
        )

    def read_lidar(self, *, sensor_name: str = "LidarSensor1") -> dict[str, Any]:
        data = self.client.getLidarData(
            lidar_name=sensor_name,
            vehicle_name=self.vehicle_name,
        )
        # Keep the native sensor-frame point cloud. A world transform requires the
        # sensor pose and LAESim configuration, so this bridge does not guess one.
        return {
            "timestamp_ns": int(data.time_stamp),
            "sensor_name": sensor_name,
            "frame": "airsim-lidar-native",
            "point_cloud_xyz": [float(value) for value in data.point_cloud],
        }

    def start_route(
        self,
        points_scene_m: Iterable[Iterable[float]],
        *,
        velocity_mps: float,
        timeout_s: float,
    ) -> Any:
        if velocity_mps <= 0.0 or timeout_s <= 0.0:
            raise ValueError("velocity_mps and timeout_s must be positive.")
        path = []
        for point in points_scene_m:
            ned = self.lookup.airsim_ned_from_canonical(tuple(point), task_id=self.task_id)
            path.append(self._airsim.Vector3r(*ned))
        if len(path) < 2:
            raise ValueError("A route must contain at least two points.")
        return self.client.moveOnPathAsync(
            path,
            float(velocity_mps),
            float(timeout_s),
            vehicle_name=self.vehicle_name,
        )

    def hover(self) -> None:
        self.client.hoverAsync(vehicle_name=self.vehicle_name).join()

    def release(self) -> None:
        if self._client is not None and self._connected:
            self.client.enableApiControl(False, vehicle_name=self.vehicle_name)
        self._connected = False

    def _task(self) -> dict[str, Any]:
        tasks = self.lookup.scene.tasks
        if self.task_id is None:
            if not tasks:
                raise ValueError("The scene has no task.")
            return tasks[0]
        task = next((item for item in tasks if str(item["task_id"]) == self.task_id), None)
        if task is None:
            raise ValueError(f"Unknown task_id: {self.task_id}")
        return task


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.x_val), float(value.y_val), float(value.z_val))
