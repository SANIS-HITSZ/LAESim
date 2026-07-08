// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef AIRLIB_HEADER_ONLY
#ifndef AIRLIB_NO_RPC

#include "vehicles/boat/api/BoatRpcLibServer.hpp"

#include "common/Common.hpp"
STRICT_MODE_OFF

#ifndef RPCLIB_MSGPACK
#define RPCLIB_MSGPACK clmdep_msgpack
#endif
#include "common/common_utils/MinWinDefines.hpp"
#undef NOUSER

#include "common/common_utils/WindowsApisCommonPre.hpp"
#undef FLOAT
#undef check
#include "rpc/server.h"
#ifndef check
#define check(expr) (static_cast<void>((expr)))
#endif
#include "common/common_utils/WindowsApisCommonPost.hpp"

#include "vehicles/boat/api/BoatRpcLibAdaptors.hpp"

STRICT_MODE_ON

namespace msr
{
namespace airlib
{
    typedef msr::airlib_rpclib::BoatRpcLibAdaptors BoatRpcLibAdaptors;

    BoatRpcLibServer::BoatRpcLibServer(ApiProvider* api_provider, string server_address, uint16_t port)
        : RpcLibServerBase(api_provider, server_address, port)
    {
        (static_cast<rpc::server*>(getServer()))->bind("getBoatState", [&](const std::string& vehicle_name) -> BoatRpcLibAdaptors::BoatState {
            return BoatRpcLibAdaptors::BoatState(getVehicleApi(vehicle_name)->getBoatState());
        });

        (static_cast<rpc::server*>(getServer()))->bind("setBoatControls", [&](const BoatRpcLibAdaptors::BoatControls& controls, const std::string& vehicle_name) -> void {
            getVehicleApi(vehicle_name)->setBoatControls(controls.to());
        });

        (static_cast<rpc::server*>(getServer()))->bind("getBoatControls", [&](const std::string& vehicle_name) -> BoatRpcLibAdaptors::BoatControls {
            return BoatRpcLibAdaptors::BoatControls(getVehicleApi(vehicle_name)->getBoatControls());
        });
    }

    BoatRpcLibServer::~BoatRpcLibServer()
    {
    }
}
} //namespace

#endif
#endif
