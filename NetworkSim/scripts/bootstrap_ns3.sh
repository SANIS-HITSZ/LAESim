#!/usr/bin/env bash
set -euo pipefail

NS3_VERSION="${NS3_VERSION:-3.48}"
NS3_TAG_OBJECT="${NS3_TAG_OBJECT:-422ef9dc12d9bcd4ee8f4b1374dffcc029a3675c}"
NS3_COMMIT="${NS3_COMMIT:-d2add90b452d600cfb4859baed8e9ea633519447}"
NS3_ROOT="${NS3_ROOT:-${HOME}/opt/ns-${NS3_VERSION}}"
NS3_REPOSITORY="${NS3_REPOSITORY:-https://gitlab.com/nsnam/ns-3-dev.git}"
CMAKE_VERSION="${CMAKE_VERSION:-3.31.6}"

export PATH="${HOME}/.local/bin:${PATH}"

compiler_major() {
    local compiler="$1"
    "${compiler}" -dumpfullversion -dumpversion 2>/dev/null | awk -F. '{print $1}'
}

ensure_gnu11_compiler() {
    if command -v gcc-11 >/dev/null 2>&1 && command -v g++-11 >/dev/null 2>&1; then
        export CC="${CC:-gcc-11}"
        export CXX="${CXX:-g++-11}"
        return
    fi

    if command -v apt-get >/dev/null 2>&1; then
        echo "GCC/G++ 11 is required by ns-${NS3_VERSION}; trying to install it with apt."
        sudo apt-get update
        if ! sudo apt-get install -y gcc-11 g++-11; then
            sudo apt-get install -y software-properties-common
            sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test
            sudo apt-get update
            sudo apt-get install -y gcc-11 g++-11
        fi
        export CC="${CC:-gcc-11}"
        export CXX="${CXX:-g++-11}"
        return
    fi

    echo "GCC/G++ 11 is required by ns-${NS3_VERSION}. Install gcc-11/g++-11 or set CC/CXX to compatible compilers." >&2
    exit 1
}

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

if [[ -z "${CC:-}" || -z "${CXX:-}" ]]; then
    ensure_gnu11_compiler
elif [[ "${CC}" == gcc* || "${CXX}" == g++* ]]; then
    cc_major="$(compiler_major "${CC}")"
    cxx_major="$(compiler_major "${CXX}")"
    if [[ -z "${cc_major}" || -z "${cxx_major}" || "${cc_major}" -lt 11 || "${cxx_major}" -lt 11 ]]; then
        echo "Configured compiler is too old for ns-${NS3_VERSION}: CC=${CC}, CXX=${CXX}" >&2
        echo "Use gcc-11/g++-11 or unset CC/CXX and rerun this script." >&2
        exit 1
    fi
fi

echo "Using compiler: CC=${CC}, CXX=${CXX}"

rm -rf "${NS3_ROOT}/cmake-cache"

./ns3 configure \
    --build-profile=release \
    --enable-examples \
    --enable-tests
./ns3 build

./ns3 run hello-simulator
./test.py -s core-example-simulator

echo "ns-${NS3_VERSION} is ready at ${NS3_ROOT}."
