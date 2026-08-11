#!/usr/bin/env bash
set -euo pipefail

ROS_DISTRO="${ROS_DISTRO:-noetic}"
TARGET_USER="${TARGET_USER:-${SUDO_USER:-}}"
ROS_APT_MIRROR="${ROS_APT_MIRROR:-https://mirrors.ustc.edu.cn/ros/ubuntu}"
ROS_KEYRING="/usr/share/keyrings/ros-archive-keyring.gpg"
ROS_SOURCE="/etc/apt/sources.list.d/ros1.list"

if [[ "${EUID}" -ne 0 ]]; then
    exec sudo --preserve-env=ROS_DISTRO,TARGET_USER,ROS_APT_MIRROR bash "$0" "$@"
fi

if [[ -z "${TARGET_USER}" ]]; then
    TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi
if [[ -z "${TARGET_USER}" || "${TARGET_USER}" == "root" ]]; then
    echo "Set TARGET_USER to the non-root Linux user that will run LAESim." >&2
    exit 1
fi

if [[ "$(. /etc/os-release && printf '%s' "${VERSION_CODENAME}")" != "focal" ]]; then
    echo "This bootstrap script requires Ubuntu 20.04 (focal)." >&2
    exit 1
fi

if ! id "${TARGET_USER}" >/dev/null 2>&1; then
    echo "Target user '${TARGET_USER}' does not exist." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# Avoid a stale or unreachable ROS source from breaking the base dependency update.
rm -f "${ROS_SOURCE}"
apt-get update
apt-get install -y --no-install-recommends \
    apt-transport-https \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    gcc-8 \
    g++-8 \
    gcc-10 \
    g++-10 \
    git \
    gnupg \
    libboost-all-dev \
    libeigen3-dev \
    libopencv-dev \
    libyaml-cpp-dev \
    lsb-release \
    ninja-build \
    pkg-config \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-yaml \
    rsync \
    software-properties-common \
    unzip \
    wget

if ! command -v gcc >/dev/null 2>&1 || ! command -v g++ >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends build-essential
fi

if [[ ! -s "${ROS_KEYRING}" ]]; then
    key_file="$(mktemp)"
    if ! curl -4 -fsSL --connect-timeout 10 --max-time 30 \
        https://gitee.com/fishros/rosdistro/raw/master/ros.asc -o "${key_file}"; then
        curl -4 -fsSL --connect-timeout 10 --max-time 30 \
            https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc -o "${key_file}"
    fi
    gpg --dearmor --yes -o "${ROS_KEYRING}" "${key_file}"
    rm -f "${key_file}"
fi
printf 'deb [signed-by=%s] %s focal main\n' "${ROS_KEYRING}" "${ROS_APT_MIRROR}" > "${ROS_SOURCE}"

apt-get update
apt-get install -y --no-install-recommends \
    python3-catkin-tools \
    python3-rosdep \
    python3-vcstool \
    "ros-${ROS_DISTRO}-cv-bridge" \
    "ros-${ROS_DISTRO}-geographic-msgs" \
    "ros-${ROS_DISTRO}-image-transport" \
    "ros-${ROS_DISTRO}-joy" \
    "ros-${ROS_DISTRO}-mavros" \
    "ros-${ROS_DISTRO}-mavros-msgs" \
    "ros-${ROS_DISTRO}-ros-base" \
    "ros-${ROS_DISTRO}-tf2-geometry-msgs" \
    "ros-${ROS_DISTRO}-tf2-sensor-msgs"

if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    if ! rosdep init; then
        pip3 install -i https://pypi.mirrors.ustc.edu.cn/simple rosdepc
        rosdepc init
        rosdepc fix-permissions
    fi
fi

if ! runuser -u "${TARGET_USER}" -- rosdep update; then
    if ! command -v rosdepc >/dev/null 2>&1; then
        pip3 install -i https://pypi.mirrors.ustc.edu.cn/simple rosdepc
    fi
    runuser -u "${TARGET_USER}" -- rosdepc update
fi

user_home="$(getent passwd "${TARGET_USER}" | cut -d: -f6)"
profile_line="source /opt/ros/${ROS_DISTRO}/setup.bash"
if ! grep -Fqx "${profile_line}" "${user_home}/.bashrc"; then
    printf '\n%s\n' "${profile_line}" >> "${user_home}/.bashrc"
fi
chown "${TARGET_USER}:${TARGET_USER}" "${user_home}/.bashrc"

echo "ROS ${ROS_DISTRO} bootstrap completed for ${TARGET_USER}."
