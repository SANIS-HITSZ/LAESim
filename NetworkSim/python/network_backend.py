#!/usr/bin/env python3
"""Communication backends shared by the LAESim ROS network bridge."""

from __future__ import annotations

import subprocess
import uuid
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


MAX_PACKET_SIZE_BYTES = 60000
MAX_PACKET_ID_LENGTH = 128
PACKET_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


@dataclass
class PacketRequest:
    source: str
    destination: str
    payload: str
    size_bytes: int
    packet_id: str = ""


@dataclass
class Delivery:
    packet_id: str
    source: str
    destination: str
    payload: str
    size_bytes: int
    simulation_time_ns: int
    latency_ns: int = 0
    link_type: str = "wifi"
    propagation_delay_ns: int = 0
    serialization_delay_ns: int = 0
    data_rate_bps: float = 0.0
    packet_error_rate: float = 0.0
    true_range_m: Optional[float] = None
    fspl_db: Optional[float] = None
    rx_power_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    frequency_hz: Optional[float] = None
    bandwidth_hz: Optional[float] = None
    route_hop_count: int = 0
    route_nodes: Optional[List[str]] = None


@dataclass(frozen=True)
class LogicalLink:
    propagation_delay_ns: int
    data_rate_bps: float
    packet_error_rate: float
    failure_reason: str
    true_range_m: float
    fspl_db: float
    rx_power_dbm: float
    snr_db: float
    frequency_hz: float
    bandwidth_hz: float


@dataclass(frozen=True)
class LogicalRoute:
    node_names: Tuple[str, ...]
    links: Tuple[LogicalLink, ...]


@dataclass
class NetworkDrop:
    packet_id: str
    source: str
    destination: str
    payload: str
    size_bytes: int
    reason: str
    simulation_time_ns: int = 0
    packet_age_ns: int = 0
    node_distance_m: Optional[float] = None
    topology_hop_count: Optional[int] = None
    route_available: Optional[bool] = None
    routing_protocol: str = ""
    max_range_m: Optional[float] = None
    source_position_m: Optional[Tuple[float, float, float]] = None
    destination_position_m: Optional[Tuple[float, float, float]] = None
    link_type: str = "wifi"
    propagation_delay_ns: int = 0
    serialization_delay_ns: int = 0
    data_rate_bps: float = 0.0
    packet_error_rate: float = 0.0
    true_range_m: Optional[float] = None
    fspl_db: Optional[float] = None
    rx_power_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    frequency_hz: Optional[float] = None
    bandwidth_hz: Optional[float] = None
    route_hop_count: int = 0
    route_nodes: Optional[List[str]] = None


def validate_request(request: PacketRequest, node_names: Iterable[str]) -> None:
    known_nodes = set(node_names)
    if request.source not in known_nodes or request.destination not in known_nodes:
        raise ValueError("source and destination must be configured LAESim vehicles")
    if not 1 <= request.size_bytes <= MAX_PACKET_SIZE_BYTES:
        raise ValueError(f"size_bytes must be between 1 and {MAX_PACKET_SIZE_BYTES}")
    if request.packet_id and (
        len(request.packet_id) > MAX_PACKET_ID_LENGTH
        or PACKET_ID_PATTERN.fullmatch(request.packet_id) is None
    ):
        raise ValueError(
            "packet_id must be at most 128 characters and contain only "
            "letters, digits, '.', '_', ':', or '-'"
        )


class DirectBackend:
    """Preserves the existing ideal-network behavior."""

    def __init__(self, node_names: Iterable[str]):
        self.node_names = list(node_names)
        self._deliveries: List[Delivery] = []

    def update_pose(self, node_name: str, x: float, y: float, z: float) -> None:
        del node_name, x, y, z

    def send(
        self,
        request: PacketRequest,
        logical_link: Optional[LogicalLink] = None,
        logical_route: Optional[LogicalRoute] = None,
    ) -> str:
        del logical_link, logical_route
        validate_request(request, self.node_names)
        packet_id = request.packet_id or uuid.uuid4().hex
        self._deliveries.append(
            Delivery(
                packet_id=packet_id,
                source=request.source,
                destination=request.destination,
                payload=request.payload,
                size_bytes=request.size_bytes,
                simulation_time_ns=0,
                latency_ns=0,
            )
        )
        return packet_id

    def step(self, milliseconds: float) -> List[Delivery]:
        del milliseconds
        deliveries = self._deliveries
        self._deliveries = []
        return deliveries

    def pop_drops(self) -> List[NetworkDrop]:
        return []

    def close(self) -> None:
        return


class Ns3Backend:
    """Line-oriented process adapter for laesim-ns3-runner."""

    def __init__(
        self,
        node_names: Iterable[str],
        runner_path: str,
        routing: str = "olsr",
        max_range: float = 250.0,
        tx_power_dbm: float = 16.0,
        warmup_seconds: float = 3.0,
        packet_timeout_seconds: float = 5.0,
    ):
        self.node_names = list(node_names)
        self.node_indexes = {name: index for index, name in enumerate(self.node_names)}
        self.pending: Dict[str, PacketRequest] = {}
        self._drops: List[NetworkDrop] = []
        command = [
            runner_path,
            f"--nodes={len(self.node_names)}",
            f"--routing={routing}",
            f"--maxRange={max_range}",
            f"--txPowerDbm={tx_power_dbm}",
            f"--warmupSeconds={warmup_seconds}",
            f"--packetTimeoutSeconds={packet_timeout_seconds}",
        ]
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready = self._read_line()
        if not ready.startswith("READY "):
            self.close()
            raise RuntimeError(f"ns-3 runner did not become ready: {ready}")

    def _write_line(self, line: str) -> None:
        if self.process.stdin is None:
            raise RuntimeError("ns-3 runner stdin is unavailable")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _read_line(self) -> str:
        if self.process.stdout is None:
            raise RuntimeError("ns-3 runner stdout is unavailable")
        line = self.process.stdout.readline()
        if not line:
            return_code = self.process.poll()
            raise RuntimeError(f"ns-3 runner exited unexpectedly ({return_code})")
        return line.strip()

    def update_pose(self, node_name: str, x: float, y: float, z: float) -> None:
        index = self.node_indexes[node_name]
        self._write_line(f"POSE {index} {x:.6f} {y:.6f} {z:.6f}")

    def send(
        self,
        request: PacketRequest,
        logical_link: Optional[LogicalLink] = None,
        logical_route: Optional[LogicalRoute] = None,
    ) -> str:
        validate_request(request, self.node_names)
        if logical_link is not None and logical_route is not None:
            raise ValueError("logical_link and logical_route are mutually exclusive")
        packet_id = request.packet_id or uuid.uuid4().hex
        request.packet_id = packet_id
        self.pending[packet_id] = request
        if logical_route is not None:
            if (
                len(logical_route.node_names) < 2
                or len(logical_route.links) != len(logical_route.node_names) - 1
                or logical_route.node_names[0] != request.source
                or logical_route.node_names[-1] != request.destination
                or any(name not in self.node_indexes for name in logical_route.node_names)
            ):
                self.pending.pop(packet_id, None)
                raise ValueError("logical route must be contiguous and match packet endpoints")
            tokens = [
                "LOGICAL_ROUTE",
                str(self.node_indexes[request.source]),
                str(self.node_indexes[request.destination]),
                str(request.size_bytes),
                packet_id,
                str(len(logical_route.links)),
            ]
            for index, link in enumerate(logical_route.links):
                tokens.extend([
                    str(self.node_indexes[logical_route.node_names[index]]),
                    str(self.node_indexes[logical_route.node_names[index + 1]]),
                    str(link.propagation_delay_ns),
                    f"{link.data_rate_bps:.6f}",
                    f"{link.packet_error_rate:.12g}",
                    link.failure_reason,
                    f"{link.true_range_m:.6f}",
                    f"{link.fspl_db:.6f}",
                    f"{link.rx_power_dbm:.6f}",
                    f"{link.snr_db:.6f}",
                    f"{link.frequency_hz:.6f}",
                    f"{link.bandwidth_hz:.6f}",
                ])
            self._write_line(" ".join(tokens))
        elif logical_link is None:
            self._write_line(
                f"SEND {self.node_indexes[request.source]} "
                f"{self.node_indexes[request.destination]} {request.size_bytes} {packet_id}"
            )
        else:
            self._write_line(
                f"LOGICAL_SEND {self.node_indexes[request.source]} "
                f"{self.node_indexes[request.destination]} {request.size_bytes} {packet_id} "
                f"{logical_link.propagation_delay_ns} {logical_link.data_rate_bps:.6f} "
                f"{logical_link.packet_error_rate:.12g} {logical_link.failure_reason} "
                f"{logical_link.true_range_m:.6f} {logical_link.fspl_db:.6f} "
                f"{logical_link.rx_power_dbm:.6f} {logical_link.snr_db:.6f} "
                f"{logical_link.frequency_hz:.6f} {logical_link.bandwidth_hz:.6f}"
            )
        return packet_id

    def step(self, milliseconds: float) -> List[Delivery]:
        self._write_line(f"STEP {milliseconds:.6f}")
        deliveries: List[Delivery] = []
        while True:
            line = self._read_line()
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "DELIVER" and len(parts) >= 5:
                packet_id = parts[1]
                request: Optional[PacketRequest] = self.pending.pop(packet_id, None)
                if request is not None:
                    delivery = Delivery(
                            packet_id=packet_id,
                            source=request.source,
                            destination=self.node_names[int(parts[2])],
                            payload=request.payload,
                            size_bytes=int(parts[3]),
                            simulation_time_ns=int(parts[4]),
                            latency_ns=int(parts[5]) if len(parts) >= 6 else 0,
                        )
                    if len(parts) >= 17:
                        delivery.link_type = parts[6]
                        delivery.propagation_delay_ns = int(parts[7])
                        delivery.serialization_delay_ns = int(parts[8])
                        delivery.data_rate_bps = float(parts[9])
                        delivery.packet_error_rate = float(parts[10])
                        delivery.true_range_m = float(parts[11])
                        delivery.fspl_db = float(parts[12])
                        delivery.rx_power_dbm = float(parts[13])
                        delivery.snr_db = float(parts[14])
                        delivery.frequency_hz = float(parts[15])
                        delivery.bandwidth_hz = float(parts[16])
                    if len(parts) >= 19:
                        delivery.route_hop_count = int(parts[17])
                        route_indexes = [int(value) for value in parts[18].split(",")]
                        delivery.route_nodes = [self.node_names[index] for index in route_indexes]
                    deliveries.append(delivery)
            elif parts[0] == "DROP" and len(parts) >= 3:
                packet_id = parts[1]
                request = self.pending.pop(packet_id, None)
                if request is not None:
                    self._drops.append(self._parse_drop(parts, request))
            elif parts[0] == "STEP_DONE":
                return deliveries
            elif parts[0] == "ERROR":
                raise RuntimeError(line)

    def _parse_drop(self, parts: List[str], request: PacketRequest) -> NetworkDrop:
        drop = NetworkDrop(
            packet_id=request.packet_id,
            source=request.source,
            destination=request.destination,
            payload=request.payload,
            size_bytes=request.size_bytes,
            reason=parts[2],
        )
        # Protocol v2 appends diagnostics after the original DROP id reason fields.
        # Keeping the short form valid allows a newly updated bridge to use an older runner.
        if len(parts) < 18:
            return drop

        source_index = int(parts[5])
        destination_index = int(parts[6])
        if source_index >= len(self.node_names) or destination_index >= len(self.node_names):
            raise RuntimeError("ns-3 runner returned an invalid node index in DROP")
        if (
            self.node_names[source_index] != request.source
            or self.node_names[destination_index] != request.destination
        ):
            raise RuntimeError("ns-3 runner returned mismatched endpoints in DROP")

        drop.simulation_time_ns = int(parts[3])
        drop.packet_age_ns = int(parts[4])
        drop.node_distance_m = float(parts[7])
        hop_count = int(parts[8])
        drop.topology_hop_count = hop_count if hop_count >= 0 else None
        drop.route_available = parts[9] == "1"
        drop.routing_protocol = parts[10]
        drop.max_range_m = float(parts[11])
        drop.source_position_m = tuple(float(value) for value in parts[12:15])
        drop.destination_position_m = tuple(float(value) for value in parts[15:18])
        if len(parts) >= 29:
            drop.link_type = parts[18]
            drop.propagation_delay_ns = int(parts[19])
            drop.serialization_delay_ns = int(parts[20])
            drop.data_rate_bps = float(parts[21])
            drop.packet_error_rate = float(parts[22])
            drop.true_range_m = float(parts[23])
            drop.fspl_db = float(parts[24])
            drop.rx_power_dbm = float(parts[25])
            drop.snr_db = float(parts[26])
            drop.frequency_hz = float(parts[27])
            drop.bandwidth_hz = float(parts[28])
        if len(parts) >= 31:
            drop.route_hop_count = int(parts[29])
            route_indexes = [int(value) for value in parts[30].split(",")]
            drop.route_nodes = [self.node_names[index] for index in route_indexes]
        return drop

    def pop_drops(self) -> List[NetworkDrop]:
        drops = self._drops
        self._drops = []
        return drops

    def metrics(self) -> str:
        self._write_line("METRICS")
        while True:
            line = self._read_line()
            if line.startswith("METRICS "):
                return line

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self._write_line("QUIT")
                self.process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=5)


def create_backend(config: dict, node_names: Iterable[str], backend_override: str = ""):
    backend_name = backend_override or str(config.get("Backend", "none")).lower()
    if backend_name == "none":
        return DirectBackend(node_names)
    if backend_name != "ns3":
        raise ValueError(f"Unsupported network backend: {backend_name}")

    runner_path = config.get(
        "RunnerPath", "~/opt/ns-3.48/build/scratch/ns3.48-laesim-ns3-runner"
    )
    return Ns3Backend(
        node_names=node_names,
        runner_path=str(__import__("os").path.expanduser(runner_path)),
        routing=str(config.get("Routing", "olsr")).lower(),
        max_range=float(config.get("MaxRangeMeters", 250.0)),
        tx_power_dbm=float(config.get("TxPowerDbm", 16.0)),
        warmup_seconds=float(config.get("WarmupSeconds", 3.0)),
        packet_timeout_seconds=float(config.get("PacketTimeoutSeconds", 5.0)),
    )
