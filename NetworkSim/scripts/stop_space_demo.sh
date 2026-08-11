#!/usr/bin/env bash
set -euo pipefail

LAESIM_HOME="${LAESIM_HOME:-${HOME}/LAESim}"
INCLUDE_NETWORK=0
if [[ "${1:-}" == "--include-network" ]]; then
    INCLUDE_NETWORK=1
fi

stop_pattern() {
    local label="$1"
    local pattern="$2"
    mapfile -t pids < <(pgrep -f "${pattern}" || true)
    if (( ${#pids[@]} == 0 )); then
        echo "${label}: not running"
        return
    fi
    echo "Stopping ${label}: ${pids[*]}"
    kill "${pids[@]}" 2>/dev/null || true
    for _ in $(seq 1 20); do
        sleep 0.1
        mapfile -t remaining < <(pgrep -f "${pattern}" || true)
        (( ${#remaining[@]} == 0 )) && return
    done
    kill -9 "${remaining[@]}" 2>/dev/null || true
}

stop_pattern "UE visualizer" "[/]space_mission_visualizer_ros.py"
stop_pattern "constellation bridge" "[/]space_constellation_bridge_ros.py"
stop_pattern "single-satellite bridge" "[/]space_mission_bridge_ros.py"
stop_pattern "unified clock" "[/]space_sim_clock.py"
if [[ "${INCLUDE_NETWORK}" == "1" ]]; then
    stop_pattern "NetworkSim bridge" "[/]ros_network_bridge.py"
fi

echo "AirSim ROS wrapper was left running."
echo "Export the finished report with:"
echo "python3 NetworkSim/python/export_space_demo_report.py --runtime-dir ${LAESIM_HOME}/.runtime/constellation_demo"
