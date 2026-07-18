#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ROS_WORKSPACE="${ROS_WORKSPACE:-${HOME}/LAESim/ros}"
SETTINGS="${SETTINGS:-}"
BACKEND="${BACKEND:-}"

if [[ -z "${SETTINGS}" ]]; then
    windows_powershell="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if [[ ! -x "${windows_powershell}" ]]; then
        echo "Set SETTINGS to the WSL path of the Windows AirSim settings.json file." >&2
        exit 1
    fi

    windows_profile="$("${windows_powershell}" -NoProfile -NonInteractive -Command '$env:USERPROFILE' | tr -d '\r')"
    SETTINGS="$(wslpath -u "${windows_profile}")/Documents/AirSim/settings.json"
fi

if [[ ! -f "${SETTINGS}" ]]; then
    echo "AirSim settings file not found at ${SETTINGS}. Set SETTINGS explicitly if it is stored elsewhere." >&2
    exit 1
fi

set +u
source /opt/ros/noetic/setup.bash
source "${ROS_WORKSPACE}/devel/setup.bash"
set -u

arguments=(--settings "${SETTINGS}")
if [[ -n "${BACKEND}" ]]; then
    arguments+=(--backend "${BACKEND}")
fi

exec python3 "${PROJECT_ROOT}/NetworkSim/python/ros_network_bridge.py" "${arguments[@]}"
