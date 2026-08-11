#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
ROS_PORT="${ROS_PORT:-11339}"
export ROS_MASTER_URI="http://127.0.0.1:${ROS_PORT}"
export ROS_HOSTNAME="127.0.0.1"

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

LOG_DIR="$(mktemp -d)"
PIDS=()
cleanup() {
    local status=$?
    for pid in "${PIDS[@]}"; do
        kill "${pid}" 2>/dev/null || true
        wait "${pid}" 2>/dev/null || true
    done
    if [[ ${status} -ne 0 ]]; then
        echo "Unified-clock test failed. Logs: ${LOG_DIR}" >&2
        for log_file in "${LOG_DIR}"/*.log; do
            [[ -f "${log_file}" ]] || continue
            echo "--- ${log_file} ---" >&2
            tail -n 100 "${log_file}" >&2
        done
    else
        rm -rf "${LOG_DIR}"
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

wait_for_topic() {
    local topic=$1
    local deadline=$((SECONDS + 20))
    until rostopic list 2>/dev/null | grep -Fxq "${topic}"; do
        (( SECONDS < deadline )) || { echo "Topic timeout: ${topic}" >&2; return 1; }
        sleep 0.2
    done
}

roscore -p "${ROS_PORT}" >"${LOG_DIR}/roscore.log" 2>&1 &
PIDS+=("$!")
sleep 1

python3 "${PROJECT_ROOT}/ros/src/example/space_sim_clock.py" \
    --start-time 2026-07-23T00:00:00Z --paused --publish-rate 20 \
    >"${LOG_DIR}/clock.log" 2>&1 &
PIDS+=("$!")
wait_for_topic "/clock"

python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" \
    --settings "${PROJECT_ROOT}/NetworkSim/config/network-simulation-unified-clock.example.json" \
    >"${LOG_DIR}/network.log" 2>&1 &
PIDS+=("$!")
wait_for_topic "/network_sim/rx/Car"

python3 "${PROJECT_ROOT}/ros/src/example/space_mission_bridge_ros.py" \
    --provider tle --tle "${PROJECT_ROOT}/Multi_use/space_mission_sample.tle" \
    --vehicle Satellite --target Car:22.591164:113.975317:0:ground \
    --clock-source ros --rate 10 \
    >"${LOG_DIR}/mission.log" 2>&1 &
PIDS+=("$!")
wait_for_topic "/space/Satellite/state"

python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_unified_clock_test.py"
echo "Unified /clock pause and step test passed."
