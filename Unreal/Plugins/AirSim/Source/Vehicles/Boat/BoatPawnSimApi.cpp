#include "BoatPawnSimApi.h"

#include "AirBlueprintLib.h"
#include "common/ClockFactory.hpp"
#include <exception>
#include <sstream>

using namespace msr::airlib;

BoatPawnSimApi::BoatPawnSimApi(const Params& params,
                               const msr::airlib::BoatApiBase::BoatControls& keyboard_controls)
    : PawnSimApi(params), keyboard_controls_(keyboard_controls)
{
}

void BoatPawnSimApi::initialize()
{
    PawnSimApi::initialize();

    std::shared_ptr<UnrealSensorFactory> sensor_factory = std::make_shared<UnrealSensorFactory>(getPawn(), &getNedTransform());
    vehicle_api_ = BoatApiFactory::createApi(getVehicleSetting(),
                                             sensor_factory,
                                             *getGroundTruthKinematics(),
                                             *getGroundTruthEnvironment());
    joystick_controls_ = msr::airlib::BoatApiBase::BoatControls();
}

std::string BoatPawnSimApi::getRecordFileLine(bool is_header_line) const
{
    std::string common_line = PawnSimApi::getRecordFileLine(is_header_line);
    if (is_header_line)
        return common_line + "Throttle\tSteering\tBrake\tAnchor\tSpeed\t";

    const auto state = getBoatState();

    std::ostringstream ss;
    ss << common_line;
    ss << current_controls_.throttle << "\t" << current_controls_.steering << "\t" << current_controls_.brake << "\t";
    ss << current_controls_.anchor << "\t" << state.speed << "\t";

    return ss.str();
}

void BoatPawnSimApi::updateRenderedState(float dt)
{
    PawnSimApi::updateRenderedState(dt);
    vehicle_api_->getStatusMessages(vehicle_api_messages_);
}

void BoatPawnSimApi::updateRendering(float dt)
{
    PawnSimApi::updateRendering(dt);

    updateBoatControls(dt);

    for (auto i = 0; i < vehicle_api_messages_.size(); ++i)
        UAirBlueprintLib::LogMessage(FString(vehicle_api_messages_[i].c_str()), TEXT(""), LogDebugLevel::Success, 30);

    try {
        vehicle_api_->sendTelemetry(dt);
    }
    catch (std::exception& e) {
        UAirBlueprintLib::LogMessage(FString(e.what()), TEXT(""), LogDebugLevel::Failure, 30);
    }
}

void BoatPawnSimApi::updateBoatControls(float dt)
{
    auto rc_data = getRCData();
    if (rc_data.is_initialized && rc_data.is_valid) {
        joystick_controls_.throttle = rc_data.throttle * 2 - 1;
        joystick_controls_.steering = rc_data.yaw;
        current_controls_ = joystick_controls_;
    }
    else {
        current_controls_ = msr::airlib::BoatApiBase::BoatControls();
    }

    if (!vehicle_api_->isApiControlEnabled()) {
        vehicle_api_->setBoatControls(current_controls_);
    }
    else {
        current_controls_ = vehicle_api_->getBoatControls();
    }

    const float max_forward_speed = 12.0f;
    const float max_reverse_speed = 3.0f;
    const float max_sway_speed = 1.8f;
    const float max_yaw_rate = FMath::DegreesToRadians(28.0f);
    const float throttle_accel = 1.9f;
    const float reverse_accel = 0.9f;
    const float brake_accel = 3.2f;
    const float anchor_accel = 5.5f;
    const float surge_linear_drag = 0.22f;
    const float surge_quad_drag = 0.035f;
    const float sway_linear_drag = 1.15f;
    const float sway_quad_drag = 0.22f;
    const float yaw_linear_drag = 1.45f;
    const float yaw_quad_drag = 0.8f;
    const float rudder_force_gain = 0.095f;
    const float rudder_moment_gain = 0.018f;

    const float throttle = FMath::Clamp(current_controls_.throttle, -1.0f, 1.0f);
    const float rudder = FMath::Clamp(current_controls_.steering, -1.0f, 1.0f);
    const float brake = FMath::Clamp(current_controls_.brake, 0.0f, 1.0f);
    const float dt_clamped = FMath::Clamp(dt, 0.0f, 0.05f);

    const float surge_sign = FMath::Sign(dynamics_.surge_velocity);
    float surge_accel = throttle * (throttle >= 0.0f ? throttle_accel : reverse_accel);
    surge_accel -= surge_linear_drag * dynamics_.surge_velocity;
    surge_accel -= surge_quad_drag * FMath::Abs(dynamics_.surge_velocity) * dynamics_.surge_velocity;

    if (brake > 0.0f)
        surge_accel -= surge_sign * brake_accel * brake;
    if (current_controls_.anchor)
        surge_accel -= surge_sign * anchor_accel;

    const float speed_for_rudder = FMath::Max(FMath::Abs(dynamics_.surge_velocity), 0.25f);
    const float rudder_dynamic_pressure = speed_for_rudder * speed_for_rudder;
    float sway_accel = rudder_force_gain * rudder * rudder_dynamic_pressure;
    sway_accel -= dynamics_.surge_velocity * dynamics_.yaw_rate;
    sway_accel -= sway_linear_drag * dynamics_.sway_velocity;
    sway_accel -= sway_quad_drag * FMath::Abs(dynamics_.sway_velocity) * dynamics_.sway_velocity;

    float yaw_accel = rudder_moment_gain * rudder * rudder_dynamic_pressure;
    yaw_accel += 0.08f * dynamics_.sway_velocity;
    yaw_accel -= yaw_linear_drag * dynamics_.yaw_rate;
    yaw_accel -= yaw_quad_drag * FMath::Abs(dynamics_.yaw_rate) * dynamics_.yaw_rate;

    dynamics_.surge_velocity += surge_accel * dt_clamped;
    dynamics_.sway_velocity += sway_accel * dt_clamped;
    dynamics_.yaw_rate += yaw_accel * dt_clamped;

    dynamics_.surge_velocity = FMath::Clamp(dynamics_.surge_velocity, -max_reverse_speed, max_forward_speed);
    dynamics_.sway_velocity = FMath::Clamp(dynamics_.sway_velocity, -max_sway_speed, max_sway_speed);
    dynamics_.yaw_rate = FMath::Clamp(dynamics_.yaw_rate, -max_yaw_rate, max_yaw_rate);

    if (FMath::Abs(dynamics_.surge_velocity) < 0.01f && FMath::Abs(throttle) < 0.01f)
        dynamics_.surge_velocity = 0.0f;
    if (FMath::Abs(dynamics_.sway_velocity) < 0.01f)
        dynamics_.sway_velocity = 0.0f;
    if (FMath::Abs(dynamics_.yaw_rate) < 0.001f)
        dynamics_.yaw_rate = 0.0f;

    APawn* pawn = getPawn();
    const float yaw_delta_deg = FMath::RadiansToDegrees(dynamics_.yaw_rate * dt_clamped);
    const FRotator next_rot(0.0f, pawn->GetActorRotation().Yaw + yaw_delta_deg, 0.0f);
    const FVector forward_move = next_rot.Vector() * dynamics_.surge_velocity * 100.0f * dt_clamped;
    const FVector right_move = FRotationMatrix(next_rot).GetScaledAxis(EAxis::Y) * dynamics_.sway_velocity * 100.0f * dt_clamped;
    const FVector next_move = forward_move + right_move;

    FHitResult hit;
    pawn->SetActorRotation(next_rot, ETeleportType::None);
    pawn->AddActorWorldOffset(next_move, true, &hit, ETeleportType::None);
    if (hit.IsValidBlockingHit()) {
        dynamics_.surge_velocity *= -0.12f;
        dynamics_.sway_velocity *= 0.2f;
        dynamics_.yaw_rate *= 0.35f;
    }

    vehicle_api_->updateBoatState(getBoatState());

    UAirBlueprintLib::LogMessageString("Boat throttle: ", std::to_string(current_controls_.throttle), LogDebugLevel::Informational);
    UAirBlueprintLib::LogMessageString("Boat steering: ", std::to_string(current_controls_.steering), LogDebugLevel::Informational);
    UAirBlueprintLib::LogMessageString("Boat speed: ", std::to_string(FMath::Abs(dynamics_.surge_velocity)), LogDebugLevel::Informational);
}

msr::airlib::BoatApiBase::BoatState BoatPawnSimApi::getBoatState() const
{
    const float speed = FMath::Sqrt(dynamics_.surge_velocity * dynamics_.surge_velocity +
                                    dynamics_.sway_velocity * dynamics_.sway_velocity);
    return msr::airlib::BoatApiBase::BoatState(
        speed,
        dynamics_.surge_velocity,
        dynamics_.sway_velocity,
        dynamics_.yaw_rate,
        current_controls_.throttle,
        current_controls_.steering,
        current_controls_.brake,
        current_controls_.anchor,
        *getGroundTruthKinematics(),
        vehicle_api_->clock()->nowNanos());
}

void BoatPawnSimApi::resetImplementation()
{
    PawnSimApi::resetImplementation();
    dynamics_ = PlanarBoatDynamics();
    current_controls_ = msr::airlib::BoatApiBase::BoatControls();
    vehicle_api_->reset();
    vehicle_api_->setBoatControls(current_controls_);
}

void BoatPawnSimApi::update()
{
    vehicle_api_->updateBoatState(getBoatState());
    vehicle_api_->update();
    PawnSimApi::update();
}

void BoatPawnSimApi::reportState(StateReporter& reporter)
{
    PawnSimApi::reportState(reporter);
    vehicle_api_->reportState(reporter);
}
