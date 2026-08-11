#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
SETTINGS="${SETTINGS:-${PROJECT_ROOT}/NetworkSim/config/network-simulation-space-access.example.json}"
ROS_PORT="${ROS_PORT:-11319}"
export ROS_MASTER_URI="http://127.0.0.1:${ROS_PORT}"
export ROS_HOSTNAME="127.0.0.1"

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

LOG_DIR="$(mktemp -d)"
ROSCORE_PID=""
NETWORK_PID=""
ACCESS_PID=""
TARGET_GPS_PID=""

cleanup() {
    local status=$?
    for pid in "${ACCESS_PID}" "${TARGET_GPS_PID}" "${NETWORK_PID}" "${ROSCORE_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
        fi
    done
    if [[ ${status} -ne 0 ]]; then
        echo "Integration test failed. Logs are in ${LOG_DIR}" >&2
        for log_file in "${LOG_DIR}"/*.log; do
            [[ -f "${log_file}" ]] || continue
            echo "--- ${log_file} ---" >&2
            tail -n 80 "${log_file}" >&2
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
        if (( SECONDS >= deadline )); then
            echo "ROS master did not start before timeout" >&2
            return 1
        fi
        sleep 0.2
    done
}

wait_for_topic() {
    local topic=$1
    local deadline=$((SECONDS + 30))
    until rostopic list 2>/dev/null | grep -Fxq "${topic}"; do
        if (( SECONDS >= deadline )); then
            echo "Topic did not appear before timeout: ${topic}" >&2
            return 1
        fi
        sleep 0.2
    done
}

start_access_publisher() {
    local min_elevation=$1
    local log_name=$2
    python3 "${PROJECT_ROOT}/ros/src/example/space_mission_bridge_ros.py" \
        --provider mock \
        --vehicle Satellite \
        --target-vehicle Car:ground \
        --min-elevation-deg "${min_elevation}" \
        --rate 5 \
        >"${LOG_DIR}/${log_name}.log" 2>&1 &
    ACCESS_PID=$!
    wait_for_topic "/space/Satellite/access/Car"
    sleep 0.5
}

roscore -p "${ROS_PORT}" >"${LOG_DIR}/roscore.log" 2>&1 &
ROSCORE_PID=$!
wait_for_master

python3 "${PROJECT_ROOT}/NetworkSim/tests/publish_dynamic_target_gps.py" \
    --vehicle Car \
    >"${LOG_DIR}/target_gps.log" 2>&1 &
TARGET_GPS_PID=$!
wait_for_topic "/airsim_node/Car/global_gps"

python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" \
    --settings "${SETTINGS}" \
    --backend ns3 \
    >"${LOG_DIR}/network_bridge.log" 2>&1 &
NETWORK_PID=$!
wait_for_topic "/network_sim/drop"
wait_for_topic "/network_sim/rx/Car"

echo "Testing visible satellite link..."
start_access_publisher 5.0 access_visible
python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_roundtrip_test.py" \
    --source Satellite \
    --destination Car \
    --expect-link-type satellite \
    --timeout 10

kill "${ACCESS_PID}"
wait "${ACCESS_PID}" 2>/dev/null || true
ACCESS_PID=""
sleep 2.2

echo "Testing blocked satellite link..."
start_access_publisher 89.9 access_blocked
python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_roundtrip_test.py" \
    --source Satellite \
    --destination Car \
    --expect-drop \
    --expect-drop-stage space_access_policy \
    --timeout 10

echo "Space-access ROS/ns-3 integration test passed."
