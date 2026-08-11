#!/usr/bin/env bash
set -euo pipefail

LAESIM_HOME="${LAESIM_HOME:-${HOME}/LAESim}"
RUNTIME_DIR="${RUNTIME_DIR:-${LAESIM_HOME}/.runtime/constellation_demo}"
mkdir -p "${RUNTIME_DIR}"

set +u
source /opt/ros/noetic/setup.bash
source "${LAESIM_HOME}/ros/devel/setup.bash"
set -u

if ! rosnode list >/dev/null 2>&1; then
    echo "ROS master is unavailable. Start the AirSim ROS wrapper first." >&2
    exit 1
fi
if ! rosnode list | grep -qx '/airsim_node'; then
    echo "/airsim_node is not registered. Enter UE Play, then restart connect_ue_ros.sh." >&2
    exit 1
fi
python3 "${LAESIM_HOME}/NetworkSim/tests/ros_ue_clock_progress_test.py" \
    --vehicle "${UE_CLOCK_VEHICLE:-Satellite}" --timeout "${UE_CLOCK_TIMEOUT:-3}"

if pgrep -f "[/]space_constellation_bridge_ros.py" >/dev/null; then
    echo "A constellation bridge is already running. Stop it before starting another demo." >&2
    exit 1
fi

setsid -f env \
    LAESIM_HOME="${LAESIM_HOME}" \
    RUNTIME_DIR="${RUNTIME_DIR}" \
    bash "${LAESIM_HOME}/NetworkSim/scripts/run_tle_constellation_demo.sh" \
    > "${RUNTIME_DIR}/constellation_launcher.log" 2>&1

READY_TIMEOUT_S="${READY_TIMEOUT_S:-120}"
if ! python3 - "${READY_TIMEOUT_S}" <<'PY'
import sys
import rospy
from std_msgs.msg import String

timeout_s = float(sys.argv[1])
rospy.init_node("laesim_space_demo_ready_check", anonymous=True, disable_signals=True)
rospy.wait_for_message("/space/selection/Car", String, timeout=timeout_s)
PY
then
    echo "Constellation bridge did not become ready within ${READY_TIMEOUT_S}s. See ${RUNTIME_DIR}/constellation_launcher.log" >&2
    exit 1
fi

if [[ "${START_VISUALIZER:-1}" == "1" ]]; then
    setsid -f env \
        LAESIM_HOME="${LAESIM_HOME}" \
        SATELLITES="${VISUAL_SATELLITES:-Satellite,Satellite2,Satellite3}" \
        TARGETS="${VISUAL_TARGETS:-UAV,UAV2,Car,Boat}" \
        bash "${LAESIM_HOME}/NetworkSim/scripts/run_space_visualization.sh" \
        > "${RUNTIME_DIR}/space_visualizer.log" 2>&1
fi

sleep 1
echo "LAESim space demo started."
echo "  runtime: ${RUNTIME_DIR}"
echo "  status:  bash NetworkSim/scripts/space_demo_status.sh"
echo "  stop:    bash NetworkSim/scripts/stop_space_demo.sh"
