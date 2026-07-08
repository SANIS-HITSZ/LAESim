// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_BoatRpcLibClient_hpp
#define air_BoatRpcLibClient_hpp

#include "api/RpcLibClientBase.hpp"
#include "vehicles/boat/api/BoatApiBase.hpp"

namespace msr
{
namespace airlib
{
    class BoatRpcLibClient : public RpcLibClientBase
    {
    public:
        BoatRpcLibClient(const string& ip_address = "localhost", uint16_t port = RpcLibPortBoat, float timeout_sec = 60);
        void setBoatControls(const BoatApiBase::BoatControls& controls, const std::string& vehicle_name = "");
        BoatApiBase::BoatState getBoatState(const std::string& vehicle_name = "");
        BoatApiBase::BoatControls getBoatControls(const std::string& vehicle_name = "");
        virtual ~BoatRpcLibClient();
    };
}
} //namespace

#endif
