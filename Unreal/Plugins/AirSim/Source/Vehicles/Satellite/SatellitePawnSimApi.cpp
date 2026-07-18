#include "SatellitePawnSimApi.h"

#include "AirBlueprintLib.h"
#include "common/ClockFactory.hpp"
#include <exception>
#include <sstream>

using namespace msr::airlib;

SatellitePawnSimApi::SatellitePawnSimApi(const Params& params,
                               const msr::airlib::SatelliteApiBase::SatelliteControls& keyboard_controls)
    : PawnSimApi(params), keyboard_controls_(keyboard_controls)
{
}

void SatellitePawnSimApi::initialize()
{
    PawnSimApi::initialize();

    std::shared_ptr<UnrealSensorFactory> sensor_factory = std::make_shared<UnrealSensorFactory>(getPawn(), &getNedTransform());
    vehicle_api_ = SatelliteApiFactory::createApi(getVehicleSetting(),
                                             sensor_factory,
                                             *getGroundTruthKinematics(),
                                             *getGroundTruthEnvironment());
    joystick_controls_ = msr::airlib::SatelliteApiBase::SatelliteControls();
}

std::string SatellitePawnSimApi::getRecordFileLine(bool is_header_line) const
{
    std::string common_line = PawnSimApi::getRecordFileLine(is_header_line);
    if (is_header_line)
        return common_line + "Vx\tVy\tVz\tYawRate\tSpeed\t";

    const auto state = getSatelliteState();

    std::ostringstream ss;
    ss << common_line;
    ss << current_controls_.vx << "\t" << current_controls_.vy << "\t" << current_controls_.vz << "\t";
    ss << current_controls_.yaw_rate << "\t" << state.speed << "\t";

    return ss.str();
}

void SatellitePawnSimApi::updateRenderedState(float dt)
{
    PawnSimApi::updateRenderedState(dt);
    vehicle_api_->getStatusMessages(vehicle_api_messages_);
}

void SatellitePawnSimApi::updateRendering(float dt)
{
    PawnSimApi::updateRendering(dt);

    updateSatelliteControls(dt);

    for (auto i = 0; i < vehicle_api_messages_.size(); ++i)
        UAirBlueprintLib::LogMessage(FString(vehicle_api_messages_[i].c_str()), TEXT(""), LogDebugLevel::Success, 30);

    try {
        vehicle_api_->sendTelemetry(dt);
    }
    catch (std::exception& e) {
        UAirBlueprintLib::LogMessage(FString(e.what()), TEXT(""), LogDebugLevel::Failure, 30);
    }
}

void SatellitePawnSimApi::updateSatelliteControls(float dt)
{
    auto rc_data = getRCData();
    if (rc_data.is_initialized && rc_data.is_valid) {
        constexpr float max_rc_speed = 25.0f;
        const float max_rc_yaw_rate = FMath::DegreesToRadians(45.0f);
        joystick_controls_.vx = (rc_data.throttle * 2 - 1) * max_rc_speed;
        joystick_controls_.vy = rc_data.roll * max_rc_speed;
        joystick_controls_.vz = -rc_data.pitch * max_rc_speed;
        joystick_controls_.yaw_rate = rc_data.yaw * max_rc_yaw_rate;
        current_controls_ = joystick_controls_;
    }
    else {
        current_controls_ = msr::airlib::SatelliteApiBase::SatelliteControls();
    }

    if (!vehicle_api_->isApiControlEnabled()) {
        vehicle_api_->setSatelliteControls(current_controls_);
    }
    else {
        current_controls_ = vehicle_api_->getSatelliteControls();
    }

    const float max_speed_axis = 500.0f;
    const float max_yaw_rate = FMath::DegreesToRadians(180.0f);
    const float dt_clamped = FMath::Clamp(dt, 0.0f, 0.05f);

    dynamics_.vx = FMath::Clamp(current_controls_.vx, -max_speed_axis, max_speed_axis);
    dynamics_.vy = FMath::Clamp(current_controls_.vy, -max_speed_axis, max_speed_axis);
    dynamics_.vz = FMath::Clamp(current_controls_.vz, -max_speed_axis, max_speed_axis);
    dynamics_.yaw_rate = FMath::Clamp(current_controls_.yaw_rate, -max_yaw_rate, max_yaw_rate);

    APawn* pawn = getPawn();
    const float yaw_delta_deg = FMath::RadiansToDegrees(dynamics_.yaw_rate * dt_clamped);
    const FRotator next_rot(0.0f, pawn->GetActorRotation().Yaw + yaw_delta_deg, 0.0f);
    const FVector next_move = getNedTransform().fromRelativeNed(Vector3r(
        dynamics_.vx * dt_clamped,
        dynamics_.vy * dt_clamped,
        dynamics_.vz * dt_clamped));

    FHitResult hit;
    pawn->SetActorRotation(next_rot, ETeleportType::None);
    pawn->AddActorWorldOffset(next_move, true, &hit, ETeleportType::None);
    if (hit.IsValidBlockingHit()) {
        dynamics_ = PointSatelliteDynamics();
    }

    vehicle_api_->updateSatelliteState(getSatelliteState());

    UAirBlueprintLib::LogMessageString("Satellite vx: ", std::to_string(dynamics_.vx), LogDebugLevel::Informational);
    UAirBlueprintLib::LogMessageString("Satellite vy: ", std::to_string(dynamics_.vy), LogDebugLevel::Informational);
    UAirBlueprintLib::LogMessageString("Satellite vz: ", std::to_string(dynamics_.vz), LogDebugLevel::Informational);
}

msr::airlib::SatelliteApiBase::SatelliteState SatellitePawnSimApi::getSatelliteState() const
{
    const float speed = FMath::Sqrt(dynamics_.vx * dynamics_.vx +
                                    dynamics_.vy * dynamics_.vy +
                                    dynamics_.vz * dynamics_.vz);
    return msr::airlib::SatelliteApiBase::SatelliteState(
        speed,
        dynamics_.vx,
        dynamics_.vy,
        dynamics_.vz,
        dynamics_.yaw_rate,
        *getGroundTruthKinematics(),
        vehicle_api_->clock()->nowNanos());
}

void SatellitePawnSimApi::resetImplementation()
{
    PawnSimApi::resetImplementation();
    dynamics_ = PointSatelliteDynamics();
    current_controls_ = msr::airlib::SatelliteApiBase::SatelliteControls();
    vehicle_api_->reset();
    vehicle_api_->setSatelliteControls(current_controls_);
}

void SatellitePawnSimApi::update()
{
    vehicle_api_->updateSatelliteState(getSatelliteState());
    vehicle_api_->update();
    PawnSimApi::update();
}

void SatellitePawnSimApi::reportState(StateReporter& reporter)
{
    PawnSimApi::reportState(reporter);
    vehicle_api_->reportState(reporter);
}
