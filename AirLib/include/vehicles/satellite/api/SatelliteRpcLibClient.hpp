// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_SatelliteRpcLibClient_hpp
#define air_SatelliteRpcLibClient_hpp

#include "api/RpcLibClientBase.hpp"
#include "vehicles/satellite/api/SatelliteApiBase.hpp"

namespace msr
{
namespace airlib
{
    class SatelliteRpcLibClient : public RpcLibClientBase
    {
    public:
        SatelliteRpcLibClient(const string& ip_address = "localhost", uint16_t port = RpcLibPortSatellite, float timeout_sec = 60);
        void setSatelliteControls(const SatelliteApiBase::SatelliteControls& controls, const std::string& vehicle_name = "");
        SatelliteApiBase::SatelliteState getSatelliteState(const std::string& vehicle_name = "");
        SatelliteApiBase::SatelliteControls getSatelliteControls(const std::string& vehicle_name = "");
        virtual ~SatelliteRpcLibClient();
    };
}
} //namespace

#endif
