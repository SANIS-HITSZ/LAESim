#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
SETTINGS="${SETTINGS:-${PROJECT_ROOT}/NetworkSim/config/network-simulation-constellation.example.json}"
TLE="${TLE:-${PROJECT_ROOT}/Multi_use/space_mission_sample.tle}"
ROS_PORT="${ROS_PORT:-11329}"
export ROS_MASTER_URI="http://127.0.0.1:${ROS_PORT}"
export ROS_HOSTNAME="127.0.0.1"

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

LOG_DIR="$(mktemp -d)"
ROSCORE_PID=""
NETWORK_PID=""
SPACE_PID=""

cleanup() {
    local status=$?
    for pid in "${SPACE_PID}" "${NETWORK_PID}" "${ROSCORE_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
        fi
    done
    if [[ ${status} -ne 0 ]]; then
        echo "Constellation integration test failed. Logs: ${LOG_DIR}" >&2
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

wait_for_master() {
    local deadline=$((SECONDS + 20))
    until rosparam list >/dev/null 2>&1; do
        (( SECONDS < deadline )) || { echo "ROS master timeout" >&2; return 1; }
        sleep 0.2
    done
}

wait_for_topic() {
    local topic=$1
    local deadline=$((SECONDS + 30))
    until rostopic list 2>/dev/null | grep -Fxq "${topic}"; do
        (( SECONDS < deadline )) || { echo "Topic timeout: ${topic}" >&2; return 1; }
        sleep 0.2
    done
}

roscore -p "${ROS_PORT}" >"${LOG_DIR}/roscore.log" 2>&1 &
ROSCORE_PID=$!
wait_for_master

python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" \
    --settings "${SETTINGS}" --backend ns3 \
    >"${LOG_DIR}/network.log" 2>&1 &
NETWORK_PID=$!
wait_for_topic "/network_sim/rx/Satellite3"

python3 "${PROJECT_ROOT}/ros/src/example/space_constellation_bridge_ros.py" \
    --satellite "Satellite=${TLE}" \
    --satellite "Satellite2=${TLE}" \
    --satellite "Satellite3=${TLE}" \
    --target Car:22.591164:113.975317:0:ground \
    --auto-next-access --access-lead-s 300 \
    --clock-speed 120 --rate 5 --duration 30 \
    >"${LOG_DIR}/constellation.log" 2>&1 &
SPACE_PID=$!
wait_for_topic "/space/selection/Car"

python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_constellation_handover_test.py" \
    --target Car --duration 6 --interval 0.5

kill "${SPACE_PID}"
wait "${SPACE_PID}" 2>/dev/null || true
SPACE_PID=""

python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_logical_route_test.py"

echo "Constellation selection and two-hop satellite route passed through ns-3 and ROS."
