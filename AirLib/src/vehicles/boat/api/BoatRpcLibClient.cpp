// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef AIRLIB_HEADER_ONLY
#ifndef AIRLIB_NO_RPC

#include "vehicles/boat/api/BoatRpcLibClient.hpp"

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

#include "vehicles/boat/api/BoatRpcLibAdaptors.hpp"

STRICT_MODE_ON
#ifdef _MSC_VER
__pragma(warning(disable : 4239))
#endif

namespace msr
{
namespace airlib
{
    typedef msr::airlib_rpclib::BoatRpcLibAdaptors BoatRpcLibAdaptors;

    BoatRpcLibClient::BoatRpcLibClient(const string& ip_address, uint16_t port, float timeout_sec)
        : RpcLibClientBase(ip_address, port, timeout_sec)
    {
    }

    BoatRpcLibClient::~BoatRpcLibClient()
    {
    }

    void BoatRpcLibClient::setBoatControls(const BoatApiBase::BoatControls& controls, const std::string& vehicle_name)
    {
        static_cast<rpc::client*>(getClient())->call("setBoatControls", BoatRpcLibAdaptors::BoatControls(controls), vehicle_name);
    }

    BoatApiBase::BoatState BoatRpcLibClient::getBoatState(const std::string& vehicle_name)
    {
        return static_cast<rpc::client*>(getClient())->call("getBoatState", vehicle_name).as<BoatRpcLibAdaptors::BoatState>().to();
    }

    BoatApiBase::BoatControls BoatRpcLibClient::getBoatControls(const std::string& vehicle_name)
    {
        return static_cast<rpc::client*>(getClient())->call("getBoatControls", vehicle_name).as<BoatRpcLibAdaptors::BoatControls>().to();
    }
}
} //namespace

#endif
#endif
