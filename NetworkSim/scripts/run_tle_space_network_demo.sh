#!/usr/bin/env bash
set -euo pipefail
trap 'status=$?; echo "ERROR: TLE demo launcher failed near line ${BASH_LINENO[0]} (exit ${status})." >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${LAESIM_HOME:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
ROS_WORKSPACE="${ROS_WORKSPACE:-${PROJECT_ROOT}/ros}"
RUNTIME_DIR="${RUNTIME_DIR:-${PROJECT_ROOT}/.runtime/tle_demo}"
TLE_FILE="${TLE_FILE:-${RUNTIME_DIR}/current.tle}"
CATALOG_NUMBER="${CATALOG_NUMBER:-25544}"
TARGET_VEHICLES="${TARGET_VEHICLES:-UAV:air,UAV2:air,Car:ground,Boat:sea}"
CLOCK_SPEED="${CLOCK_SPEED:-60}"
RATE_HZ="${RATE_HZ:-5}"
MIN_ELEVATION_DEG="${MIN_ELEVATION_DEG:-5}"
ACCESS_LEAD_S="${ACCESS_LEAD_S:-300}"
DISPLAY_RADIUS="${DISPLAY_RADIUS:-80}"
DISPLAY_ALTITUDE="${DISPLAY_ALTITUDE:-300}"
DURATION="${DURATION:-0}"
REFRESH_TLE="${REFRESH_TLE:-1}"
DRIVE_LAESIM="${DRIVE_LAESIM:-1}"
START_NETWORK_BRIDGE="${START_NETWORK_BRIDGE:-1}"
RESTART_SPACE_BRIDGE="${RESTART_SPACE_BRIDGE:-1}"

SPACE_SCRIPT="${PROJECT_ROOT}/ros/src/example/space_mission_bridge_ros.py"
NETWORK_SCRIPT="${PROJECT_ROOT}/NetworkSim/scripts/run_ros_network_bridge.sh"
SPACE_LOG="${RUNTIME_DIR}/space_tle_bridge.log"
NETWORK_LOG="${RUNTIME_DIR}/network_bridge.log"
MISSION_JSONL="${RUNTIME_DIR}/space_tle_runtime.jsonl"
SUMMARY_JSON="${RUNTIME_DIR}/space_tle_summary.json"

mkdir -p "${RUNTIME_DIR}"
: > "${SPACE_LOG}"
exec > >(tee -a "${SPACE_LOG}") 2>&1

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

topic_exists() {
    rostopic list 2>/dev/null | awk -v expected="$1" '$0 == expected { found = 1 } END { exit !found }'
}

echo "LAESim TLE space/network demo"
echo "  PROJECT_ROOT=${PROJECT_ROOT}"
echo "  TLE_FILE=${TLE_FILE}"
echo "  TARGET_VEHICLES=${TARGET_VEHICLES}"
echo "  CLOCK_SPEED=${CLOCK_SPEED}"
echo "  RUNTIME_DIR=${RUNTIME_DIR}"

if ! rosnode list >/dev/null 2>&1; then
    echo "ROS master is unavailable. Start connect_ue_ros.sh first." >&2
    exit 1
fi
if ! topic_exists "/airsim_node/Satellite/global_gps"; then
    echo "AirSim ROS wrapper is not publishing /airsim_node/Satellite/global_gps." >&2
    exit 1
fi

python3 -c "import sgp4" >/dev/null
if [[ "${DRIVE_LAESIM}" == "1" ]]; then
    PYTHONPATH="${PROJECT_ROOT}/PythonClient${PYTHONPATH:+:${PYTHONPATH}}" \
        python3 -c "import airsim, msgpackrpc" >/dev/null
fi

if [[ "${REFRESH_TLE}" == "1" ]]; then
    echo "Refreshing TLE from CelesTrak catalog ${CATALOG_NUMBER}..."
    if ! python3 "${PROJECT_ROOT}/Multi_use/update_tle.py" \
        --catalog-number "${CATALOG_NUMBER}" \
        --output "${TLE_FILE}"; then
        if [[ ! -f "${TLE_FILE}" ]]; then
            echo "TLE refresh failed and no cached TLE is available." >&2
            exit 1
        fi
        echo "WARNING: TLE refresh failed; using cached ${TLE_FILE}." >&2
    fi
fi
if [[ ! -f "${TLE_FILE}" ]]; then
    echo "TLE file not found: ${TLE_FILE}" >&2
    exit 1
fi

if [[ "${START_NETWORK_BRIDGE}" == "1" ]] && \
   ! pgrep -f "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" >/dev/null; then
    echo "Starting NetworkSim ROS bridge..."
    setsid -f bash "${NETWORK_SCRIPT}" > "${NETWORK_LOG}" 2>&1
    for _ in $(seq 1 30); do
        if topic_exists "/network_sim/rx/Satellite"; then
            break
        fi
        sleep 0.5
    done
fi
if ! topic_exists "/network_sim/rx/Satellite"; then
    echo "NetworkSim bridge is not publishing /network_sim/rx/Satellite." >&2
    echo "See ${NETWORK_LOG}" >&2
    exit 1
fi

mapfile -t existing_space_pids < <(pgrep -f "python3 .*${SPACE_SCRIPT}" || true)
if (( ${#existing_space_pids[@]} > 0 )); then
    if [[ "${RESTART_SPACE_BRIDGE}" != "1" ]]; then
        echo "A space mission bridge is already running: ${existing_space_pids[*]}" >&2
        exit 1
    fi
    echo "Stopping previous space mission bridge: ${existing_space_pids[*]}"
    kill "${existing_space_pids[@]}"
    sleep 2
fi

WIN_IP="${WIN_IP:-$(ip route | awk '/default/ && !found { value = $3; found = 1 } END { print value }')}"
if [[ "${DRIVE_LAESIM}" == "1" && -z "${WIN_IP}" ]]; then
    echo "Failed to resolve the Windows host IP." >&2
    exit 1
fi

arguments=(
    --provider tle
    --tle "${TLE_FILE}"
    --require-fresh-tle
    --vehicle Satellite
    --rate "${RATE_HZ}"
    --duration "${DURATION}"
    --clock-speed "${CLOCK_SPEED}"
    --auto-next-access
    --access-lead-s "${ACCESS_LEAD_S}"
    --min-elevation-deg "${MIN_ELEVATION_DEG}"
    --display-mode global-track
    --global-track-radius "${DISPLAY_RADIUS}"
    --fixed-display-altitude "${DISPLAY_ALTITUDE}"
    --mission-report-jsonl "${MISSION_JSONL}"
    --runtime-summary-json "${SUMMARY_JSON}"
)

IFS=',' read -ra targets <<< "${TARGET_VEHICLES}"
for target in "${targets[@]}"; do
    [[ -n "${target}" ]] && arguments+=(--target-vehicle "${target}")
done

if [[ "${DRIVE_LAESIM}" == "1" ]]; then
    arguments+=(--drive-laesim --host "${WIN_IP}")
fi

echo "Starting real TLE bridge. Press Ctrl+C to close the current access window and write the summary."
echo "  WIN_IP=${WIN_IP:-not-used}"
echo "  MISSION_JSONL=${MISSION_JSONL}"
echo "  SUMMARY_JSON=${SUMMARY_JSON}"

exec env PYTHONUNBUFFERED=1 python3 "${SPACE_SCRIPT}" "${arguments[@]}"
