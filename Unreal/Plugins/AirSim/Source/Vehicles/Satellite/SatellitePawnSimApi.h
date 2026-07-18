#pragma once

#include "CoreMinimal.h"

#include "SatellitePawn.h"
#include "PawnSimApi.h"
#include "UnrealSensors/UnrealSensorFactory.h"
#include "common/Common.hpp"
#include "common/CommonStructs.hpp"
#include "physics/Kinematics.hpp"
#include "vehicles/satellite/SatelliteApiFactory.hpp"
#include "vehicles/satellite/api/SatelliteApiBase.hpp"

class SatellitePawnSimApi : public PawnSimApi
{
public:
    typedef msr::airlib::StateReporter StateReporter;

public:
    SatellitePawnSimApi(const Params& params,
                   const msr::airlib::SatelliteApiBase::SatelliteControls& keyboard_controls);
    virtual void initialize() override;
    virtual ~SatellitePawnSimApi() = default;

    virtual void update() override;
    virtual void reportState(StateReporter& reporter) override;
    virtual std::string getRecordFileLine(bool is_header_line) const override;
    virtual void updateRenderedState(float dt) override;
    virtual void updateRendering(float dt) override;

    msr::airlib::SatelliteApiBase* getVehicleApi() const
    {
        return vehicle_api_.get();
    }

    virtual msr::airlib::VehicleApiBase* getVehicleApiBase() const override
    {
        return vehicle_api_.get();
    }

protected:
    virtual void resetImplementation() override;

private:
    void updateSatelliteControls(float dt);
    msr::airlib::SatelliteApiBase::SatelliteState getSatelliteState() const;

private:
    struct PointSatelliteDynamics
    {
        float vx = 0.0f; // NED X velocity, m/s
        float vy = 0.0f; // NED Y velocity, m/s
        float vz = 0.0f; // NED Z velocity, m/s
        float yaw_rate = 0.0f; // rad/s
    };

    std::unique_ptr<msr::airlib::SatelliteApiBase> vehicle_api_;
    std::vector<std::string> vehicle_api_messages_;
    const msr::airlib::SatelliteApiBase::SatelliteControls& keyboard_controls_;
    msr::airlib::SatelliteApiBase::SatelliteControls joystick_controls_;
    msr::airlib::SatelliteApiBase::SatelliteControls current_controls_;
    PointSatelliteDynamics dynamics_;
};
