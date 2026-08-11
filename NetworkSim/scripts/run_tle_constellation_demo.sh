#!/usr/bin/env bash
set -euo pipefail
trap 'status=$?; echo "ERROR: constellation demo failed near line ${BASH_LINENO[0]} (exit ${status})." >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${LAESIM_HOME:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
ROS_WORKSPACE="${ROS_WORKSPACE:-${PROJECT_ROOT}/ros}"
RUNTIME_DIR="${RUNTIME_DIR:-${PROJECT_ROOT}/.runtime/constellation_demo}"
SATELLITES="${SATELLITES:-Satellite:25544,Satellite2:25338,Satellite3:39084}"
TARGET_VEHICLES="${TARGET_VEHICLES:-UAV:air,UAV2:air,Car:ground,Boat:sea}"
CLOCK_SPEED="${CLOCK_SPEED:-120}"
RATE_HZ="${RATE_HZ:-2}"
POSE_RATE_HZ="${POSE_RATE_HZ:-0.5}"
MIN_ELEVATION_DEG="${MIN_ELEVATION_DEG:-5}"
ACCESS_LEAD_S="${ACCESS_LEAD_S:-300}"
DISPLAY_RADIUS="${DISPLAY_RADIUS:-80}"
DISPLAY_ALTITUDE="${DISPLAY_ALTITUDE:-300}"
SELECTION_HYSTERESIS_DEG="${SELECTION_HYSTERESIS_DEG:-2}"
SELECTION_MIN_HOLD_S="${SELECTION_MIN_HOLD_S:-10}"
PUBLISH_ISL="${PUBLISH_ISL:-1}"
MAX_ISL_RANGE_M="${MAX_ISL_RANGE_M:-5000000}"
DURATION="${DURATION:-0}"
REFRESH_TLE="${REFRESH_TLE:-1}"
DRIVE_LAESIM="${DRIVE_LAESIM:-1}"
RPC_TIMEOUT="${RPC_TIMEOUT:-5}"
START_NETWORK_BRIDGE="${START_NETWORK_BRIDGE:-1}"

SPACE_SCRIPT="${PROJECT_ROOT}/ros/src/example/space_constellation_bridge_ros.py"
NETWORK_SCRIPT="${PROJECT_ROOT}/NetworkSim/scripts/run_ros_network_bridge.sh"
SPACE_LOG="${RUNTIME_DIR}/space_constellation_bridge.log"
NETWORK_LOG="${RUNTIME_DIR}/network_bridge.log"
MISSION_JSONL="${RUNTIME_DIR}/space_constellation_runtime.jsonl"
SUMMARY_JSON="${RUNTIME_DIR}/space_constellation_summary.json"

mkdir -p "${RUNTIME_DIR}/tle"
: > "${SPACE_LOG}"
exec > >(tee -a "${SPACE_LOG}") 2>&1

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

topic_exists() {
    rostopic list 2>/dev/null | awk -v expected="$1" '$0 == expected { found = 1 } END { exit !found }'
}

if ! rosnode list >/dev/null 2>&1; then
    echo "ROS master is unavailable. Start connect_ue_ros.sh first." >&2
    exit 1
fi

python3 -c "import sgp4" >/dev/null
if [[ "${DRIVE_LAESIM}" == "1" ]]; then
    PYTHONPATH="${PROJECT_ROOT}/PythonClient${PYTHONPATH:+:${PYTHONPATH}}" \
        python3 -c "import airsim, msgpackrpc" >/dev/null
fi

arguments=(
    --provider tle
    --rate "${RATE_HZ}"
    --duration "${DURATION}"
    --clock-speed "${CLOCK_SPEED}"
    --auto-next-access
    --access-lead-s "${ACCESS_LEAD_S}"
    --min-elevation-deg "${MIN_ELEVATION_DEG}"
    --selection-hysteresis-deg "${SELECTION_HYSTERESIS_DEG}"
    --selection-min-hold-s "${SELECTION_MIN_HOLD_S}"
    --rpc-timeout "${RPC_TIMEOUT}"
    --laesim-pose-rate "${POSE_RATE_HZ}"
    --display-mode global-track
    --global-track-radius "${DISPLAY_RADIUS}"
    --fixed-display-altitude "${DISPLAY_ALTITUDE}"
    --mission-report-jsonl "${MISSION_JSONL}"
    --runtime-summary-json "${SUMMARY_JSON}"
)

if [[ "${PUBLISH_ISL}" == "1" ]]; then
    arguments+=(--publish-isl --max-isl-range-m "${MAX_ISL_RANGE_M}")
fi

IFS=',' read -ra satellite_specs <<< "${SATELLITES}"
for item in "${satellite_specs[@]}"; do
    vehicle="${item%%:*}"
    catalog="${item#*:}"
    if [[ -z "${vehicle}" || -z "${catalog}" || "${vehicle}" == "${catalog}" ]]; then
        echo "Invalid SATELLITES item: ${item}; expected VEHICLE:CATALOG_NUMBER" >&2
        exit 1
    fi
    tle_file="${RUNTIME_DIR}/tle/${vehicle}-${catalog}.tle"
    if [[ "${REFRESH_TLE}" == "1" ]]; then
        echo "Refreshing ${vehicle} from CelesTrak catalog ${catalog}..."
        if ! python3 "${PROJECT_ROOT}/Multi_use/update_tle.py" \
            --catalog-number "${catalog}" --output "${tle_file}"; then
            if [[ ! -f "${tle_file}" ]]; then
                echo "TLE refresh failed and no cache exists for ${vehicle}." >&2
                exit 1
            fi
            echo "WARNING: using cached TLE for ${vehicle}." >&2
        fi
    fi
    if [[ ! -f "${tle_file}" ]]; then
        echo "TLE file not found: ${tle_file}" >&2
        exit 1
    fi
    if ! topic_exists "/airsim_node/${vehicle}/global_gps"; then
        echo "Missing /airsim_node/${vehicle}/global_gps. Add ${vehicle} to settings.json and restart UE." >&2
        exit 1
    fi
    arguments+=(--satellite "${vehicle}=${tle_file}")
done

IFS=',' read -ra targets <<< "${TARGET_VEHICLES}"
for target in "${targets[@]}"; do
    [[ -n "${target}" ]] && arguments+=(--target-vehicle "${target}")
done

if [[ "${START_NETWORK_BRIDGE}" == "1" ]] && \
   ! pgrep -f "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" >/dev/null; then
    echo "Starting NetworkSim ROS bridge..."
    setsid -f bash "${NETWORK_SCRIPT}" > "${NETWORK_LOG}" 2>&1
    for _ in $(seq 1 30); do
        topic_exists "/network_sim/rx/Satellite2" && break
        sleep 0.5
    done
fi
if ! topic_exists "/network_sim/rx/Satellite2"; then
    echo "NetworkSim was started without Satellite2/Satellite3. Restart it after updating settings.json." >&2
    exit 1
fi

mapfile -t old_pids < <(pgrep -f "python3 .*space_(mission|constellation)_bridge_ros.py" || true)
if (( ${#old_pids[@]} > 0 )); then
    echo "Stopping previous space bridge: ${old_pids[*]}"
    kill "${old_pids[@]}"
    sleep 2
fi

WIN_IP="${WIN_IP:-$(ip route | awk '/default/ && !found { value = $3; found = 1 } END { print value }')}"
if [[ "${DRIVE_LAESIM}" == "1" ]]; then
    [[ -n "${WIN_IP}" ]] || { echo "Failed to resolve Windows host IP." >&2; exit 1; }
    arguments+=(--drive-laesim --host "${WIN_IP}")
fi

echo "Starting LAESim constellation demo"
echo "  SATELLITES=${SATELLITES}"
echo "  TARGET_VEHICLES=${TARGET_VEHICLES}"
echo "  CLOCK_SPEED=${CLOCK_SPEED}"
echo "  RATE_HZ=${RATE_HZ} POSE_RATE_HZ=${POSE_RATE_HZ}"
echo "  WIN_IP=${WIN_IP:-not-used}"
echo "  SUMMARY_JSON=${SUMMARY_JSON}"
echo "Press Ctrl+C to stop and write the summary."

exec env PYTHONUNBUFFERED=1 python3 "${SPACE_SCRIPT}" "${arguments[@]}"
