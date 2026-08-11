#!/usr/bin/env bash
set -euo pipefail

LAESIM_HOME="${LAESIM_HOME:-${HOME}/LAESim}"
HOST="${HOST:-$(ip route show default | awk '{print $3; exit}')}"
SATELLITES="${SATELLITES:-Satellite,Satellite2,Satellite3}"
TARGETS="${TARGETS:-UAV,UAV2,Car,Boat}"
SETTINGS="${SETTINGS:-}"

if [[ -z "${SETTINGS}" ]]; then
    for candidate in /mnt/c/Users/*/Documents/AirSim/settings.json; do
        if [[ -f "${candidate}" ]]; then
            SETTINGS="${candidate}"
            break
        fi
    done
fi
if [[ -z "${SETTINGS}" || ! -f "${SETTINGS}" ]]; then
    echo "AirSim settings.json not found. Set SETTINGS=/mnt/c/Users/<user>/Documents/AirSim/settings.json." >&2
    exit 1
fi

set +u
source /opt/ros/noetic/setup.bash
source "${LAESIM_HOME}/ros/devel/setup.bash"
set -u

args=(
    --settings "${SETTINGS}"
    --host "${HOST}"
    --global-track-radius "${GLOBAL_TRACK_RADIUS:-80}"
    --min-elevation-deg "${MIN_ELEVATION_DEG:-5}"
    --surface-z "${SURFACE_Z:-0}"
    --rate "${VISUAL_RATE_HZ:-0.5}"
    --timeout "${VISUAL_RPC_TIMEOUT:-3}"
    --max-consecutive-errors "${VISUAL_MAX_ERRORS:-3}"
    --constellation-timeout "${CONSTELLATION_TIMEOUT:-10}"
)
IFS=',' read -r -a satellite_names <<< "${SATELLITES}"
for satellite in "${satellite_names[@]}"; do
    args+=(--satellite "${satellite}")
done
IFS=',' read -r -a target_names <<< "${TARGETS}"
for target in "${target_names[@]}"; do
    args+=(--target "${target}")
done

echo "Starting UE space mission visualization"
echo "  HOST=${HOST}"
echo "  SETTINGS=${SETTINGS}"
echo "  SATELLITES=${SATELLITES}"
echo "  TARGETS=${TARGETS}"
exec env PYTHONUNBUFFERED=1 python3 \
    "${LAESIM_HOME}/ros/src/example/space_mission_visualizer_ros.py" "${args[@]}"
