// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_SatelliteRpcLibServer_hpp
#define air_SatelliteRpcLibServer_hpp

#include "api/RpcLibServerBase.hpp"
#include "vehicles/satellite/api/SatelliteApiBase.hpp"

namespace msr
{
namespace airlib
{
    class SatelliteRpcLibServer : public RpcLibServerBase
    {
    public:
        SatelliteRpcLibServer(ApiProvider* api_provider, string server_address, uint16_t port = RpcLibPortSatellite);
        virtual ~SatelliteRpcLibServer();

    protected:
        virtual SatelliteApiBase* getVehicleApi(const std::string& vehicle_name) override
        {
            return static_cast<SatelliteApiBase*>(RpcLibServerBase::getVehicleApi(vehicle_name));
        }
    };
}
} //namespace

#endif
