// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#ifndef air_BoatRpcLibAdaptors_hpp
#define air_BoatRpcLibAdaptors_hpp

#include "api/RpcLibAdaptorsBase.hpp"
#include "common/Common.hpp"
#include "common/CommonStructs.hpp"
#include "vehicles/boat/api/BoatApiBase.hpp"

#include "common/common_utils/WindowsApisCommonPre.hpp"
#include "rpc/msgpack.hpp"
#include "common/common_utils/WindowsApisCommonPost.hpp"

namespace msr
{
namespace airlib_rpclib
{
    class BoatRpcLibAdaptors : public RpcLibAdaptorsBase
    {
    public:
        struct BoatControls
        {
            float throttle = 0;
            float steering = 0;
            float brake = 0;
            bool anchor = false;

            MSGPACK_DEFINE_MAP(throttle, steering, brake, anchor);

            BoatControls()
            {
            }

            BoatControls(const msr::airlib::BoatApiBase::BoatControls& s)
            {
                throttle = s.throttle;
                steering = s.steering;
                brake = s.brake;
                anchor = s.anchor;
            }

            msr::airlib::BoatApiBase::BoatControls to() const
            {
                return msr::airlib::BoatApiBase::BoatControls(throttle, steering, brake, anchor);
            }
        };

        struct BoatState
        {
            float speed;
            float forward_speed;
            float lateral_speed;
            float yaw_rate;
            float throttle;
            float steering;
            float brake;
            bool anchor;
            KinematicsState kinematics_estimated;
            uint64_t timestamp;

            MSGPACK_DEFINE_MAP(speed, forward_speed, lateral_speed, yaw_rate, throttle, steering, brake, anchor, kinematics_estimated, timestamp);

            BoatState()
            {
            }

            BoatState(const msr::airlib::BoatApiBase::BoatState& s)
            {
                speed = s.speed;
                forward_speed = s.forward_speed;
                lateral_speed = s.lateral_speed;
                yaw_rate = s.yaw_rate;
                throttle = s.throttle;
                steering = s.steering;
                brake = s.brake;
                anchor = s.anchor;
                kinematics_estimated = s.kinematics_estimated;
                timestamp = s.timestamp;
            }

            msr::airlib::BoatApiBase::BoatState to() const
            {
                return msr::airlib::BoatApiBase::BoatState(speed, forward_speed, lateral_speed, yaw_rate,
                                                           throttle, steering, brake, anchor, kinematics_estimated.to(), timestamp);
            }
        };
    };
}
} //namespace

#endif
