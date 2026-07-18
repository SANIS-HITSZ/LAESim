#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NS3_ROOT="${NS3_ROOT:-${HOME}/opt/ns-3.48}"
SOURCE_FILE="${PROJECT_ROOT}/NetworkSim/ns3/laesim-ns3-runner.cc"
TARGET_FILE="${NS3_ROOT}/scratch/laesim-ns3-runner.cc"

export PATH="${HOME}/.local/bin:${PATH}"

if [[ ! -x "${NS3_ROOT}/ns3" ]]; then
    echo "ns-3 is not installed at ${NS3_ROOT}." >&2
    exit 1
fi

install -m 0644 "${SOURCE_FILE}" "${TARGET_FILE}"
cd "${NS3_ROOT}"
./ns3 build

runner="${NS3_ROOT}/build/scratch/ns3.48-laesim-ns3-runner"
if [[ ! -x "${runner}" ]]; then
    echo "Runner was not produced at ${runner}." >&2
    exit 1
fi

echo "LAESim ns-3 runner is ready at ${runner}."
