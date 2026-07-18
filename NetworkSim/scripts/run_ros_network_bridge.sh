#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
SETTINGS="${SETTINGS:-/mnt/c/Users/10852/Documents/AirSim/settings.json}"
BACKEND="${BACKEND:-}"

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

arguments=(--settings "${SETTINGS}")
if [[ -n "${BACKEND}" ]]; then
    arguments+=(--backend "${BACKEND}")
fi

exec python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" "${arguments[@]}"
