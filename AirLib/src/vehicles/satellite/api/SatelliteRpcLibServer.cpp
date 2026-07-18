// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef AIRLIB_HEADER_ONLY
#ifndef AIRLIB_NO_RPC

#include "vehicles/satellite/api/SatelliteRpcLibServer.hpp"

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

#include "vehicles/satellite/api/SatelliteRpcLibAdaptors.hpp"

STRICT_MODE_ON

namespace msr
{
namespace airlib
{
    typedef msr::airlib_rpclib::SatelliteRpcLibAdaptors SatelliteRpcLibAdaptors;

    SatelliteRpcLibServer::SatelliteRpcLibServer(ApiProvider* api_provider, string server_address, uint16_t port)
        : RpcLibServerBase(api_provider, server_address, port)
    {
        (static_cast<rpc::server*>(getServer()))->bind("getSatelliteState", [&](const std::string& vehicle_name) -> SatelliteRpcLibAdaptors::SatelliteState {
            return SatelliteRpcLibAdaptors::SatelliteState(getVehicleApi(vehicle_name)->getSatelliteState());
        });

        (static_cast<rpc::server*>(getServer()))->bind("setSatelliteControls", [&](const SatelliteRpcLibAdaptors::SatelliteControls& controls, const std::string& vehicle_name) -> void {
            getVehicleApi(vehicle_name)->setSatelliteControls(controls.to());
        });

        (static_cast<rpc::server*>(getServer()))->bind("getSatelliteControls", [&](const std::string& vehicle_name) -> SatelliteRpcLibAdaptors::SatelliteControls {
            return SatelliteRpcLibAdaptors::SatelliteControls(getVehicleApi(vehicle_name)->getSatelliteControls());
        });
    }

    SatelliteRpcLibServer::~SatelliteRpcLibServer()
    {
    }
}
} //namespace

#endif
#endif
