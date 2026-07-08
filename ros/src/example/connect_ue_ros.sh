#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROS_WS="$(cd "${SCRIPT_DIR}/../.." && pwd)"

set +u
if [[ -f "/opt/ros/noetic/setup.bash" ]]; then
  source "/opt/ros/noetic/setup.bash"
fi

if [[ -f "${ROS_WS}/devel/setup.bash" ]]; then
  # Make the script self-contained when launched directly from ros/src/example.
  source "${ROS_WS}/devel/setup.bash"
fi
set -u

WIN_IP="${WIN_IP:-$(ip route | awk '/default/ {print $3; exit}')}"

if [[ -z "${WIN_IP}" ]]; then
  echo "Failed to resolve Windows host IP from default route." >&2
  exit 1
fi

echo "WIN_IP=${WIN_IP}"
echo "Launching airsim_node -> host:=${WIN_IP}"

exec roslaunch airsim_ros_pkgs airsim_node.launch output:=screen host:="${WIN_IP}"
