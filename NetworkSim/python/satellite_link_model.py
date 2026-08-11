#!/usr/bin/env python3
"""Link-budget model for LAESim satellite logical links."""

from __future__ import annotations

import math
from typing import Optional

from network_backend import LogicalLink, PacketRequest


SPEED_OF_LIGHT_MPS = 299_792_458.0
BOLTZMANN_NOISE_DBM_PER_HZ = -174.0


class SatelliteLinkModel:
    def __init__(self, network_config: dict):
        config = network_config.get("SatelliteLinkModel", {})
        self.enabled = bool(config.get("Enabled", False))
        self.frequency_hz = float(config.get("FrequencyHz", 2.2e9))
        self.bandwidth_hz = float(config.get("BandwidthHz", 5.0e6))
        self.data_rate_bps = float(config.get("DataRateBps", 2.0e6))
        self.tx_power_dbm = float(config.get("TxPowerDbm", 40.0))
        self.tx_gain_dbi = float(config.get("TxAntennaGainDbi", 10.0))
        self.rx_gain_dbi = float(config.get("RxAntennaGainDbi", 20.0))
        self.system_loss_db = float(config.get("SystemLossDb", 2.0))
        self.noise_figure_db = float(config.get("NoiseFigureDb", 3.0))
        self.min_snr_db = float(config.get("MinSnrDb", 3.0))
        self.packet_error_model = str(config.get("PacketErrorModel", "bpsk")).lower()

        positive = {
            "FrequencyHz": self.frequency_hz,
            "BandwidthHz": self.bandwidth_hz,
            "DataRateBps": self.data_rate_bps,
        }
        for name, value in positive.items():
            if value <= 0.0:
                raise ValueError(f"NetworkSimulation.SatelliteLinkModel.{name} must be positive")
        if self.packet_error_model not in ("bpsk", "none"):
            raise ValueError(
                "NetworkSimulation.SatelliteLinkModel.PacketErrorModel must be 'bpsk' or 'none'"
            )

    def build(self, request: PacketRequest, access_decision) -> Optional[LogicalLink]:
        if not self.enabled or not access_decision.topic:
            return None
        range_m = float(access_decision.range_m)
        if not math.isfinite(range_m) or range_m <= 0.0:
            raise ValueError("satellite logical link requires a finite positive access range_m")

        wavelength_m = SPEED_OF_LIGHT_MPS / self.frequency_hz
        fspl_db = 20.0 * math.log10(4.0 * math.pi * range_m / wavelength_m)
        rx_power_dbm = (
            self.tx_power_dbm
            + self.tx_gain_dbi
            + self.rx_gain_dbi
            - self.system_loss_db
            - fspl_db
        )
        noise_power_dbm = (
            BOLTZMANN_NOISE_DBM_PER_HZ
            + 10.0 * math.log10(self.bandwidth_hz)
            + self.noise_figure_db
        )
        snr_db = rx_power_dbm - noise_power_dbm

        packet_error_rate = 0.0
        failure_reason = "link_error"
        if snr_db < self.min_snr_db:
            packet_error_rate = 1.0
            failure_reason = "link_budget"
        elif self.packet_error_model == "bpsk":
            eb_n0_db = snr_db + 10.0 * math.log10(self.bandwidth_hz / self.data_rate_bps)
            bit_error_rate = 0.5 * math.erfc(math.sqrt(10.0 ** (eb_n0_db / 10.0)))
            bit_count = max(1, request.size_bytes * 8)
            if bit_error_rate >= 1.0:
                packet_error_rate = 1.0
            elif bit_error_rate > 0.0:
                packet_error_rate = -math.expm1(bit_count * math.log1p(-bit_error_rate))
            packet_error_rate = min(max(packet_error_rate, 0.0), 1.0)

        return LogicalLink(
            propagation_delay_ns=max(1, round(range_m / SPEED_OF_LIGHT_MPS * 1e9)),
            data_rate_bps=self.data_rate_bps,
            packet_error_rate=packet_error_rate,
            failure_reason=failure_reason,
            true_range_m=range_m,
            fspl_db=fspl_db,
            rx_power_dbm=rx_power_dbm,
            snr_db=snr_db,
            frequency_hz=self.frequency_hz,
            bandwidth_hz=self.bandwidth_hz,
        )
