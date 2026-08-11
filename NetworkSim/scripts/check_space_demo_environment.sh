#!/usr/bin/env bash
set -euo pipefail

LAESIM_HOME="${LAESIM_HOME:-${HOME}/LAESim}"
set +u
[[ -f /opt/ros/noetic/setup.bash ]] && source /opt/ros/noetic/setup.bash
[[ -f "${LAESIM_HOME}/ros/devel/setup.bash" ]] && source "${LAESIM_HOME}/ros/devel/setup.bash"
set -u

exec python3 "${LAESIM_HOME}/NetworkSim/scripts/space_demo_doctor.py" "$@"
