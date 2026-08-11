#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAESIM_HOME="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NS3_ROOT="${NS3_ROOT:-${HOME}/opt/ns-3.48}"

export LAESIM_HOME
export NS3_ROOT
export PATH="${HOME}/.local/bin:${PATH}"

echo "LAESIM_HOME=${LAESIM_HOME}"
echo "NS3_ROOT=${NS3_ROOT}"

missing=()
for command_name in git python3; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        missing+=("${command_name}")
    fi
done

if ((${#missing[@]} > 0)); then
    echo "Missing required tools: ${missing[*]}" >&2
    if command -v apt-get >/dev/null 2>&1; then
        echo "Trying to install required packages with apt. Sudo may ask for your password."
        sudo apt-get update
        sudo apt-get install -y git python3 python3-pip software-properties-common
    else
        echo "Please install the missing tools, then rerun this script." >&2
        exit 1
    fi
fi

bash "${LAESIM_HOME}/NetworkSim/scripts/bootstrap_ns3.sh"
bash "${LAESIM_HOME}/NetworkSim/scripts/build_ns3_runner.sh"

runner="${NS3_ROOT}/build/scratch/ns3.48-laesim-ns3-runner"
if [[ ! -x "${runner}" ]]; then
    echo "Runner was not produced at ${runner}." >&2
    exit 1
fi

echo "Runner exists:"
ls -l "${runner}"

python3 "${LAESIM_HOME}/NetworkSim/tests/smoke_backend.py" \
    --runner "${runner}" \
    --require-ns3

echo "LAESim ns-3 runner build and smoke test finished."
