from types import SimpleNamespace

import pytest
from laesim_radio.laesim_bridge import LAESimBridge


class Future:
    def __init__(self) -> None:
        self.joined = False

    def join(self) -> None:
        self.joined = True


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def confirmConnection(self):
        self.calls.append(("confirm",))

    def enableApiControl(self, enabled, **kwargs):
        self.calls.append(("api", enabled, kwargs))

    def armDisarm(self, armed, **kwargs):
        self.calls.append(("arm", armed, kwargs))

    def takeoffAsync(self, **kwargs):
        self.calls.append(("takeoff", kwargs))
        return Future()

    def moveToZAsync(self, z, speed, **kwargs):
        self.calls.append(("z", z, speed, kwargs))
        return Future()

    def hoverAsync(self, **kwargs):
        self.calls.append(("hover", kwargs))
        return Future()

    def moveOnPathAsync(self, path, speed, timeout, **kwargs):
        self.calls.append(("path", path, speed, timeout, kwargs))
        return Future()

    def getMultirotorState(self, **kwargs):
        def vector(x, y, z):
            return SimpleNamespace(x_val=x, y_val=y, z_val=z)
        return SimpleNamespace(
            timestamp=123,
            kinematics_estimated=SimpleNamespace(
                position=vector(2.0, 3.0, -4.0),
                linear_velocity=vector(1.0, 0.0, 0.0),
            ),
        )

    def simGetCollisionInfo(self, **kwargs):
        return SimpleNamespace(has_collided=False, object_name="")

    def getLidarData(self, **kwargs):
        return SimpleNamespace(time_stamp=456, point_cloud=[1.0, 2.0, 3.0])


class FakeLookup:
    def __init__(self) -> None:
        self.scene = SimpleNamespace(
            tasks=[{"task_id": "task-000", "start_m": [10.0, 20.0, 50.0]}]
        )

    def canonical_from_airsim_ned(self, point, *, task_id=None):
        north, east, down = point
        return (10.0 + north, 20.0 - east, 50.0 - down)

    def airsim_ned_from_canonical(self, point, *, task_id=None):
        x, y, z = point
        return (x - 10.0, 20.0 - y, 50.0 - z)


class FakeAirSim:
    class Vector3r:
        def __init__(self, x, y, z):
            self.x_val, self.y_val, self.z_val = x, y, z


def test_bridge_connects_reads_state_and_preserves_lidar_frame() -> None:
    client = FakeClient()
    bridge = LAESimBridge(FakeLookup(), airsim_module=FakeAirSim, client=client)
    bridge.connect()
    state = bridge.read_state()
    lidar = bridge.read_lidar()
    assert state.position_scene_m == pytest.approx((12.0, 17.0, 54.0))
    assert state.velocity_ned_mps == pytest.approx((1.0, 0.0, 0.0))
    assert lidar["frame"] == "airsim-lidar-native"
    assert lidar["point_cloud_xyz"] == [1.0, 2.0, 3.0]
    bridge.release()
    assert client.calls[-1][0:2] == ("api", False)


def test_bridge_prepares_altitude_and_converts_route_to_ned() -> None:
    client = FakeClient()
    bridge = LAESimBridge(FakeLookup(), airsim_module=FakeAirSim, client=client)
    bridge.connect()
    bridge.prepare_flight(65.0, vertical_speed_mps=4.0)
    future = bridge.start_route(
        [(10.0, 20.0, 65.0), (15.0, 18.0, 65.0)],
        velocity_mps=3.0,
        timeout_s=10.0,
    )
    z_call = next(call for call in client.calls if call[0] == "z")
    path_call = next(call for call in client.calls if call[0] == "path")
    assert z_call[1:3] == pytest.approx((-15.0, 4.0))
    assert (path_call[1][1].x_val, path_call[1][1].y_val, path_call[1][1].z_val) == pytest.approx(
        (5.0, 2.0, -15.0)
    )
    assert future.joined is False
