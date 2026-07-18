#!/usr/bin/env python3
"""Communication backends shared by the LAESim ROS network bridge."""

from __future__ import annotations

import subprocess
import uuid
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


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

    def send(self, request: PacketRequest) -> str:
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
            )
        )
        return packet_id

    def step(self, milliseconds: float) -> List[Delivery]:
        del milliseconds
        deliveries = self._deliveries
        self._deliveries = []
        return deliveries

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

    def send(self, request: PacketRequest) -> str:
        validate_request(request, self.node_names)
        packet_id = request.packet_id or uuid.uuid4().hex
        request.packet_id = packet_id
        self.pending[packet_id] = request
        self._write_line(
            f"SEND {self.node_indexes[request.source]} "
            f"{self.node_indexes[request.destination]} {request.size_bytes} {packet_id}"
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
            if parts[0] == "DELIVER" and len(parts) == 5:
                packet_id = parts[1]
                request: Optional[PacketRequest] = self.pending.pop(packet_id, None)
                if request is not None:
                    deliveries.append(
                        Delivery(
                            packet_id=packet_id,
                            source=request.source,
                            destination=self.node_names[int(parts[2])],
                            payload=request.payload,
                            size_bytes=int(parts[3]),
                            simulation_time_ns=int(parts[4]),
                        )
                    )
            elif parts[0] == "DROP" and len(parts) >= 2:
                self.pending.pop(parts[1], None)
            elif parts[0] == "STEP_DONE":
                return deliveries
            elif parts[0] == "ERROR":
                raise RuntimeError(line)

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
