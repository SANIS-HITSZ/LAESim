#pragma once

#include "CoreMinimal.h"

#include "BoatPawn.h"
#include "PawnSimApi.h"
#include "UnrealSensors/UnrealSensorFactory.h"
#include "common/Common.hpp"
#include "common/CommonStructs.hpp"
#include "physics/Kinematics.hpp"
#include "vehicles/boat/BoatApiFactory.hpp"
#include "vehicles/boat/api/BoatApiBase.hpp"

class BoatPawnSimApi : public PawnSimApi
{
public:
    typedef msr::airlib::StateReporter StateReporter;

public:
    BoatPawnSimApi(const Params& params,
                   const msr::airlib::BoatApiBase::BoatControls& keyboard_controls);
    virtual void initialize() override;
    virtual ~BoatPawnSimApi() = default;

    virtual void update() override;
    virtual void reportState(StateReporter& reporter) override;
    virtual std::string getRecordFileLine(bool is_header_line) const override;
    virtual void updateRenderedState(float dt) override;
    virtual void updateRendering(float dt) override;

    msr::airlib::BoatApiBase* getVehicleApi() const
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
    void updateBoatControls(float dt);
    msr::airlib::BoatApiBase::BoatState getBoatState() const;

private:
    struct PlanarBoatDynamics
    {
        float surge_velocity = 0.0f; // body-forward speed, m/s
        float sway_velocity = 0.0f; // body-right speed, m/s
        float yaw_rate = 0.0f; // rad/s
    };

    std::unique_ptr<msr::airlib::BoatApiBase> vehicle_api_;
    std::vector<std::string> vehicle_api_messages_;
    const msr::airlib::BoatApiBase::BoatControls& keyboard_controls_;
    msr::airlib::BoatApiBase::BoatControls joystick_controls_;
    msr::airlib::BoatApiBase::BoatControls current_controls_;
    PlanarBoatDynamics dynamics_;
};
