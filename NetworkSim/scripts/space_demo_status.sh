#!/usr/bin/env bash
set -u

LAESIM_HOME="${LAESIM_HOME:-${HOME}/LAESim}"
set +u
source /opt/ros/noetic/setup.bash 2>/dev/null || true
source "${LAESIM_HOME}/ros/devel/setup.bash" 2>/dev/null || true
set -u

show_process() {
    local label="$1"
    local pattern="$2"
    local pids
    pids="$(pgrep -f "${pattern}" | tr '\n' ' ' || true)"
    printf '%-24s %s\n' "${label}" "${pids:-STOPPED}"
}

echo "Processes"
show_process "AirSim roslaunch" "airsim_node.launch"
show_process "NetworkSim bridge" "[/]ros_network_bridge.py"
show_process "Constellation bridge" "[/]space_constellation_bridge_ros.py"
show_process "UE visualizer" "[/]space_mission_visualizer_ros.py"
show_process "Unified clock" "[/]space_sim_clock.py"

echo
echo "ROS topics"
if rosnode list >/dev/null 2>&1; then
    topic_count="$(rostopic list | wc -l)"
    state_count="$(rostopic list | grep -Ec '^/space/Satellite[0-9]*/state$' || true)"
    selection_count="$(rostopic list | grep -Ec '^/space/selection/' || true)"
    rx_count="$(rostopic list | grep -Ec '^/network_sim/rx/' || true)"
    echo "  total=${topic_count} satellite_states=${state_count} selections=${selection_count} network_rx=${rx_count}"
    if rostopic list | grep -qx '/space/visualization/status'; then
        echo "  visualization status: /space/visualization/status"
    else
        echo "  visualization status: NOT PUBLISHED"
    fi
    if ! rosnode list | grep -qx '/airsim_node'; then
        echo "  /airsim_node: NOT REGISTERED (restart the wrapper after UE enters Play)"
    elif python3 "${LAESIM_HOME}/NetworkSim/tests/ros_ue_clock_progress_test.py" \
        --vehicle "${UE_CLOCK_VEHICLE:-Satellite}" --timeout "${UE_CLOCK_TIMEOUT:-2}"; then
        echo "  UE simulation clock: RUNNING"
    else
        echo "  UE simulation clock: FROZEN OR NO DATA"
    fi
else
    echo "  ROS master: UNAVAILABLE"
fi
