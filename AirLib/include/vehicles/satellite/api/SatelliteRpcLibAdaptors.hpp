// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_SatelliteRpcLibAdaptors_hpp
#define air_SatelliteRpcLibAdaptors_hpp

#include "api/RpcLibAdaptorsBase.hpp"
#include "common/Common.hpp"
#include "common/CommonStructs.hpp"
#include "vehicles/satellite/api/SatelliteApiBase.hpp"

#include "common/common_utils/WindowsApisCommonPre.hpp"
#include "rpc/msgpack.hpp"
#include "common/common_utils/WindowsApisCommonPost.hpp"

namespace msr
{
namespace airlib_rpclib
{
    class SatelliteRpcLibAdaptors : public RpcLibAdaptorsBase
    {
    public:
        struct SatelliteControls
        {
            float vx = 0;
            float vy = 0;
            float vz = 0;
            float yaw_rate = 0;

            MSGPACK_DEFINE_MAP(vx, vy, vz, yaw_rate);

            SatelliteControls()
            {
            }

            SatelliteControls(const msr::airlib::SatelliteApiBase::SatelliteControls& s)
            {
                vx = s.vx;
                vy = s.vy;
                vz = s.vz;
                yaw_rate = s.yaw_rate;
            }

            msr::airlib::SatelliteApiBase::SatelliteControls to() const
            {
                return msr::airlib::SatelliteApiBase::SatelliteControls(vx, vy, vz, yaw_rate);
            }
        };

        struct SatelliteState
        {
            float speed;
            float vx;
            float vy;
            float vz;
            float yaw_rate;
            KinematicsState kinematics_estimated;
            uint64_t timestamp;

            MSGPACK_DEFINE_MAP(speed, vx, vy, vz, yaw_rate, kinematics_estimated, timestamp);

            SatelliteState()
            {
            }

            SatelliteState(const msr::airlib::SatelliteApiBase::SatelliteState& s)
            {
                speed = s.speed;
                vx = s.vx;
                vy = s.vy;
                vz = s.vz;
                yaw_rate = s.yaw_rate;
                kinematics_estimated = s.kinematics_estimated;
                timestamp = s.timestamp;
            }

            msr::airlib::SatelliteApiBase::SatelliteState to() const
            {
                return msr::airlib::SatelliteApiBase::SatelliteState(speed, vx, vy, vz, yaw_rate,
                                                                     kinematics_estimated.to(), timestamp);
            }
        };
    };
}
} //namespace

#endif
