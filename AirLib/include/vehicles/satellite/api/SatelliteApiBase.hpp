// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.
#ifndef air_SatelliteApiBase_hpp
#define air_SatelliteApiBase_hpp

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
    class SatelliteApiBase : public VehicleApiBase
    {
    public:
        struct SatelliteControls
        {
            float vx = 0; // NED X velocity, m/s
            float vy = 0; // NED Y velocity, m/s
            float vz = 0; // NED Z velocity, m/s. Positive is down.
            float yaw_rate = 0; // rad/s

            SatelliteControls()
            {
            }

            SatelliteControls(float vx_val, float vy_val, float vz_val, float yaw_rate_val)
                : vx(vx_val), vy(vy_val), vz(vz_val), yaw_rate(yaw_rate_val)
            {
            }
        };

        struct SatelliteState
        {
            float speed = 0;
            float vx = 0;
            float vy = 0;
            float vz = 0;
            float yaw_rate = 0;
            Kinematics::State kinematics_estimated;
            uint64_t timestamp = 0;

            SatelliteState()
            {
            }

            SatelliteState(float speed_val, float vx_val, float vy_val, float vz_val, float yaw_rate_val,
                           const Kinematics::State& kinematics_estimated_val, uint64_t timestamp_val)
                : speed(speed_val)
                , vx(vx_val)
                , vy(vy_val)
                , vz(vz_val)
                , yaw_rate(yaw_rate_val)
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
        SatelliteApiBase(const AirSimSettings::VehicleSetting* vehicle_setting,
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

        virtual void setSatelliteControls(const SatelliteControls& controls) = 0;
        virtual void updateSatelliteState(const SatelliteState& state) = 0;
        virtual const SatelliteState& getSatelliteState() const = 0;
        virtual const SatelliteControls& getSatelliteControls() const = 0;
        virtual ~SatelliteApiBase() = default;

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
