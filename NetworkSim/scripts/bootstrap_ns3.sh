#!/usr/bin/env bash
set -euo pipefail

NS3_VERSION="${NS3_VERSION:-3.48}"
NS3_TAG_OBJECT="${NS3_TAG_OBJECT:-422ef9dc12d9bcd4ee8f4b1374dffcc029a3675c}"
NS3_COMMIT="${NS3_COMMIT:-d2add90b452d600cfb4859baed8e9ea633519447}"
NS3_ROOT="${NS3_ROOT:-${HOME}/opt/ns-${NS3_VERSION}}"
NS3_REPOSITORY="${NS3_REPOSITORY:-https://gitlab.com/nsnam/ns-3-dev.git}"
CMAKE_VERSION="${CMAKE_VERSION:-3.31.6}"

export PATH="${HOME}/.local/bin:${PATH}"

current_cmake_version="$(cmake --version 2>/dev/null | head -n 1 | awk '{print $3}')"
if [[ -z "${current_cmake_version}" ]] || \
    [[ "$(printf '%s\n' "${current_cmake_version}" 3.25 | sort -V | head -n 1)" != "3.25" ]]; then
    python3 -m pip install --user \
        --index-url https://pypi.mirrors.ustc.edu.cn/simple \
        "cmake==${CMAKE_VERSION}"
fi

mkdir -p "$(dirname "${NS3_ROOT}")"

if [[ ! -d "${NS3_ROOT}/.git" ]]; then
    git clone --branch "ns-${NS3_VERSION}" --depth 1 "${NS3_REPOSITORY}" "${NS3_ROOT}"
fi

cd "${NS3_ROOT}"
actual_tag_object="$(git rev-parse "refs/tags/ns-${NS3_VERSION}")"
actual_commit="$(git rev-parse HEAD)"
if [[ "${actual_tag_object}" != "${NS3_TAG_OBJECT}" ]]; then
    echo "Unexpected ns-3 tag object: ${actual_tag_object}; expected ${NS3_TAG_OBJECT}." >&2
    exit 1
fi
if [[ "${actual_commit}" != "${NS3_COMMIT}" ]]; then
    echo "Unexpected ns-3 commit: ${actual_commit}; expected ${NS3_COMMIT}." >&2
    exit 1
fi

export CC="${CC:-gcc-11}"
export CXX="${CXX:-g++-11}"

./ns3 configure \
    --build-profile=release \
    --enable-examples \
    --enable-tests
./ns3 build

./ns3 run hello-simulator
./test.py -s core-example-simulator

echo "ns-${NS3_VERSION} is ready at ${NS3_ROOT}."
