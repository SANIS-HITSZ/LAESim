// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef AIRLIB_HEADER_ONLY
#ifndef AIRLIB_NO_RPC

#include "vehicles/satellite/api/SatelliteRpcLibClient.hpp"

#include "common/ClockFactory.hpp"
#include "common/Common.hpp"
#include <thread>
STRICT_MODE_OFF

#ifndef RPCLIB_MSGPACK
#define RPCLIB_MSGPACK clmdep_msgpack
#endif

#ifdef nil
#undef nil
#endif

#include "common/common_utils/WindowsApisCommonPre.hpp"
#undef FLOAT
#undef check
#include "rpc/client.h"
#ifndef check
#define check(expr) (static_cast<void>((expr)))
#endif
#include "common/common_utils/WindowsApisCommonPost.hpp"

#include "vehicles/satellite/api/SatelliteRpcLibAdaptors.hpp"

STRICT_MODE_ON
#ifdef _MSC_VER
__pragma(warning(disable : 4239))
#endif

namespace msr
{
namespace airlib
{
    typedef msr::airlib_rpclib::SatelliteRpcLibAdaptors SatelliteRpcLibAdaptors;

    SatelliteRpcLibClient::SatelliteRpcLibClient(const string& ip_address, uint16_t port, float timeout_sec)
        : RpcLibClientBase(ip_address, port, timeout_sec)
    {
    }

    SatelliteRpcLibClient::~SatelliteRpcLibClient()
    {
    }

    void SatelliteRpcLibClient::setSatelliteControls(const SatelliteApiBase::SatelliteControls& controls, const std::string& vehicle_name)
    {
        static_cast<rpc::client*>(getClient())->call("setSatelliteControls", SatelliteRpcLibAdaptors::SatelliteControls(controls), vehicle_name);
    }

    SatelliteApiBase::SatelliteState SatelliteRpcLibClient::getSatelliteState(const std::string& vehicle_name)
    {
        return static_cast<rpc::client*>(getClient())->call("getSatelliteState", vehicle_name).as<SatelliteRpcLibAdaptors::SatelliteState>().to();
    }

    SatelliteApiBase::SatelliteControls SatelliteRpcLibClient::getSatelliteControls(const std::string& vehicle_name)
    {
        return static_cast<rpc::client*>(getClient())->call("getSatelliteControls", vehicle_name).as<SatelliteRpcLibAdaptors::SatelliteControls>().to();
    }
}
} //namespace

#endif
#endif
