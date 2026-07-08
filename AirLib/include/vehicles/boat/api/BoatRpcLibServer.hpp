// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_BoatRpcLibServer_hpp
#define air_BoatRpcLibServer_hpp

#include "api/RpcLibServerBase.hpp"
#include "vehicles/boat/api/BoatApiBase.hpp"

namespace msr
{
namespace airlib
{
    class BoatRpcLibServer : public RpcLibServerBase
    {
    public:
        BoatRpcLibServer(ApiProvider* api_provider, string server_address, uint16_t port = RpcLibPortBoat);
        virtual ~BoatRpcLibServer();

    protected:
        virtual BoatApiBase* getVehicleApi(const std::string& vehicle_name) override
        {
            return static_cast<BoatApiBase*>(RpcLibServerBase::getVehicleApi(vehicle_name));
        }
    };
}
} //namespace

#endif
