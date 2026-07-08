// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
#ifndef air_BoatApiBase_hpp
#define air_BoatApiBase_hpp

#include "api/VehicleApiBase.hpp"
#include "common/AirSimSettings.hpp"
#include "common/CommonStructs.hpp"
#include "common/VectorMath.hpp"
#include "physics/Environment.hpp"
#include "physics/Kinematics.hpp"
#include "sensors/SensorBase.hpp"
#include "sensors/SensorCollection.hpp"
#include "sensors/SensorFactory.hpp"

namespace msr
{
namespace airlib
{
    class BoatApiBase : public VehicleApiBase
    {
    public:
        struct BoatControls
        {
            float throttle = 0; // -1 reverse, +1 forward
            float steering = 0; // -1 right, +1 left in AirSim FLU convention
            float brake = 0;
            bool anchor = false;

            BoatControls()
            {
            }

            BoatControls(float throttle_val, float steering_val, float brake_val, bool anchor_val)
                : throttle(throttle_val), steering(steering_val), brake(brake_val), anchor(anchor_val)
            {
            }
        };

        struct BoatState
        {
            float speed = 0;
            float forward_speed = 0;
            float lateral_speed = 0;
            float yaw_rate = 0;
            float throttle = 0;
            float steering = 0;
            float brake = 0;
            bool anchor = false;
            Kinematics::State kinematics_estimated;
            uint64_t timestamp = 0;

            BoatState()
            {
            }

            BoatState(float speed_val, float forward_speed_val, float lateral_speed_val, float yaw_rate_val,
                      float throttle_val, float steering_val, float brake_val, bool anchor_val,
                      const Kinematics::State& kinematics_estimated_val, uint64_t timestamp_val)
                : speed(speed_val)
                , forward_speed(forward_speed_val)
                , lateral_speed(lateral_speed_val)
                , yaw_rate(yaw_rate_val)
                , throttle(throttle_val)
                , steering(steering_val)
                , brake(brake_val)
                , anchor(anchor_val)
                , kinematics_estimated(kinematics_estimated_val)
                , timestamp(timestamp_val)
            {
            }

            const Vector3r& getPosition() const
            {
                return kinematics_estimated.pose.position;
            }

            const Quaternionr& getOrientation() const
            {
                return kinematics_estimated.pose.orientation;
            }
        };

    public:
        BoatApiBase(const AirSimSettings::VehicleSetting* vehicle_setting,
                    std::shared_ptr<SensorFactory> sensor_factory,
                    const Kinematics::State& state, const Environment& environment)
        {
            initialize(vehicle_setting, sensor_factory, state, environment);
        }

        virtual void update() override
        {
            VehicleApiBase::update();
            getSensors().update();
        }

        void reportState(StateReporter& reporter) override
        {
            getSensors().reportState(reporter);
        }

        virtual const SensorCollection& getSensors() const override
        {
            return sensors_;
        }

        SensorCollection& getSensors()
        {
            return sensors_;
        }

        void initialize(const AirSimSettings::VehicleSetting* vehicle_setting,
                        std::shared_ptr<SensorFactory> sensor_factory,
                        const Kinematics::State& state, const Environment& environment)
        {
            sensor_factory_ = sensor_factory;
            sensor_storage_.clear();
            sensors_.clear();
            addSensorsFromSettings(vehicle_setting);
            getSensors().initialize(&state, &environment);
        }

        void addSensorsFromSettings(const AirSimSettings::VehicleSetting* vehicle_setting)
        {
            const auto& sensor_settings = vehicle_setting->sensors;
            sensor_factory_->createSensorsFromSettings(sensor_settings, sensors_, sensor_storage_, vehicle_setting->vehicle_type);
        }

        virtual void setBoatControls(const BoatControls& controls) = 0;
        virtual void updateBoatState(const BoatState& state) = 0;
        virtual const BoatState& getBoatState() const = 0;
        virtual const BoatControls& getBoatControls() const = 0;
        virtual ~BoatApiBase() = default;

        std::shared_ptr<const SensorFactory> sensor_factory_;
        SensorCollection sensors_;
        vector<shared_ptr<SensorBase>> sensor_storage_;

    protected:
        virtual void resetImplementation() override
        {
            getSensors().reset();
        }
    };
}
} //namespace
#endif
