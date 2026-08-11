#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
SETTINGS="${SETTINGS:-${PROJECT_ROOT}/NetworkSim/config/network-simulation-delivery-acceptance.json}"
ROS_PORT="${ROS_PORT:-11339}"
OUTPUT="${OUTPUT:-${PROJECT_ROOT}/.runtime/delivery_acceptance/acceptance_report.json}"
export ROS_MASTER_URI="http://127.0.0.1:${ROS_PORT}"
export ROS_HOSTNAME="127.0.0.1"

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

LOG_DIR="$(mktemp -d)"
ROSCORE_PID=""
NETWORK_PID=""

cleanup() {
    local status=$?
    for pid in "${NETWORK_PID}" "${ROSCORE_PID}"; do
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
        fi
    done
    if [[ ${status} -ne 0 ]]; then
        echo "Space delivery acceptance failed. Logs: ${LOG_DIR}" >&2
        for log_file in "${LOG_DIR}"/*.log; do
            [[ -f "${log_file}" ]] || continue
            echo "--- ${log_file} ---" >&2
            tail -n 120 "${log_file}" >&2
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

runner_path="$(python3 - "${SETTINGS}" <<'PY'
import json, os, sys
with open(sys.argv[1], encoding="utf-8-sig") as handle:
    settings = json.load(handle)
path = settings["NetworkSimulation"]["RunnerPath"]
print(os.path.expanduser(path))
PY
)"
if [[ ! -x "${runner_path}" ]]; then
    echo "ns-3 runner is missing or not executable: ${runner_path}" >&2
    echo "Run: bash NetworkSim/scripts/build_and_verify_ns3_runner.sh" >&2
    exit 1
fi

mkdir -p "$(dirname "${OUTPUT}")"
roscore -p "${ROS_PORT}" >"${LOG_DIR}/roscore.log" 2>&1 &
ROSCORE_PID=$!
wait_for_master

python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" \
    --settings "${SETTINGS}" --backend ns3 \
    >"${LOG_DIR}/network.log" 2>&1 &
NETWORK_PID=$!
wait_for_topic "/network_sim/drop"
wait_for_topic "/network_sim/rx/Car"

python3 "${PROJECT_ROOT}/NetworkSim/tests/ros_space_delivery_acceptance.py" \
    --output "${OUTPUT}"

echo "Deterministic space delivery acceptance passed."
echo "Report: ${OUTPUT}"
