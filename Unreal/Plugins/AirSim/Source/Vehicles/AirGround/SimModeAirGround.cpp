#include "SimModeAirGround.h"

#include "AirBlueprintLib.h"
#include "Vehicles/Car/CarPawnSimApi.h"
#include "Vehicles/Multirotor/MultirotorPawnSimApi.h"
#include "api/MultiPortApiServer.hpp"
#include "common/ClockFactory.hpp"
#include "common/ScalableClock.hpp"
#include "common/SteppableClock.hpp"
#include <stdexcept>

void ASimModeAirGround::BeginPlay()
{
    Super::BeginPlay();
    initializeForPlay();
}

void ASimModeAirGround::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    stopAsyncUpdator();
    Super::EndPlay(EndPlayReason);
}

void ASimModeAirGround::setupClockSpeed()
{
    typedef msr::airlib::ClockFactory ClockFactory;

    const float clock_speed = getSettings().clock_speed;
    const std::string clock_type = getSettings().clock_type;

    if (clock_type == "ScalableClock") {
        ClockFactory::get(std::make_shared<msr::airlib::ScalableClock>(clock_speed == 1 ? 1 : 1 / clock_speed));
    }
    else if (clock_type == "SteppableClock") {
        if (clock_speed >= 1) {
            ClockFactory::get(std::make_shared<msr::airlib::SteppableClock>(
                static_cast<msr::airlib::TTimeDelta>(getPhysicsLoopPeriod() * 1E-9)));

            setPhysicsLoopPeriod(getPhysicsLoopPeriod() / static_cast<long long>(clock_speed));
        }
        else {
            ClockFactory::get(std::make_shared<msr::airlib::SteppableClock>(
                static_cast<msr::airlib::TTimeDelta>(getPhysicsLoopPeriod() * 1E-9 * clock_speed)));
        }
    }
    else {
        throw std::invalid_argument(common_utils::Utils::stringf(
            "clock_type %s is not recognized", clock_type.c_str()));
    }
}

std::unique_ptr<msr::airlib::ApiServerBase> ASimModeAirGround::createApiServer() const
{
#ifdef AIRLIB_NO_RPC
    return ASimModeBase::createApiServer();
#else
    return std::unique_ptr<msr::airlib::ApiServerBase>(new msr::airlib::MultiPortApiServer(
        getApiProvider(),
        getSettings().api_server_address,
        static_cast<uint16_t>(getSettings().api_port_cv),
        static_cast<uint16_t>(getSettings().api_port_car),
        static_cast<uint16_t>(getSettings().api_port_multirotor)));
#endif
}

void ASimModeAirGround::getExistingVehiclePawns(TArray<AActor*>& pawns) const
{
    TArray<AActor*> drone_pawns;
    TArray<AActor*> car_pawns;
    UAirBlueprintLib::FindAllActor<AFlyingPawn>(this, drone_pawns);
    UAirBlueprintLib::FindAllActor<ACarPawn>(this, car_pawns);

    pawns.Append(drone_pawns);
    pawns.Append(car_pawns);
}

bool ASimModeAirGround::isVehicleTypeSupported(const std::string& vehicle_type) const
{
    return AirSimSettings::isMultirotor(vehicle_type) || AirSimSettings::isCar(vehicle_type);
}

std::string ASimModeAirGround::getVehiclePawnPathName(const AirSimSettings::VehicleSetting& vehicle_setting) const
{
    if (!vehicle_setting.pawn_path.empty())
        return vehicle_setting.pawn_path;

    return AirSimSettings::isCar(vehicle_setting.vehicle_type) ? "DefaultCar" : "DefaultQuadrotor";
}

PawnEvents* ASimModeAirGround::getVehiclePawnEvents(APawn* pawn) const
{
    if (auto* car_pawn = Cast<ACarPawn>(pawn))
        return car_pawn->getPawnEvents();

    return static_cast<AFlyingPawn*>(pawn)->getPawnEvents();
}

const common_utils::UniqueValueMap<std::string, APIPCamera*> ASimModeAirGround::getVehiclePawnCameras(APawn* pawn) const
{
    if (auto* car_pawn = Cast<ACarPawn>(pawn))
        return car_pawn->getCameras();

    return static_cast<AFlyingPawn*>(pawn)->getCameras();
}

void ASimModeAirGround::initializeVehiclePawn(APawn* pawn)
{
    if (auto* car_pawn = Cast<ACarPawn>(pawn)) {
        car_pawn->initializeForBeginPlay(getSettings().engine_sound);
        return;
    }

    static_cast<AFlyingPawn*>(pawn)->initializeForBeginPlay();
}

std::unique_ptr<PawnSimApi> ASimModeAirGround::createVehicleSimApi(
    const PawnSimApi::Params& pawn_sim_api_params) const
{
    if (Cast<ACarPawn>(pawn_sim_api_params.pawn) != nullptr) {
        auto* vehicle_pawn = static_cast<ACarPawn*>(pawn_sim_api_params.pawn);
        auto vehicle_sim_api = std::unique_ptr<PawnSimApi>(new CarPawnSimApi(
            pawn_sim_api_params, vehicle_pawn->getKeyBoardControls()));
        vehicle_sim_api->initialize();
        vehicle_sim_api->reset();
        return vehicle_sim_api;
    }

    auto vehicle_sim_api = std::unique_ptr<PawnSimApi>(new MultirotorPawnSimApi(pawn_sim_api_params));
    vehicle_sim_api->initialize();
    return vehicle_sim_api;
}

msr::airlib::VehicleApiBase* ASimModeAirGround::getVehicleApi(const PawnSimApi::Params& pawn_sim_api_params,
                                                              const PawnSimApi* sim_api) const
{
    if (Cast<ACarPawn>(pawn_sim_api_params.pawn) != nullptr)
        return static_cast<const CarPawnSimApi*>(sim_api)->getVehicleApi();

    return static_cast<const MultirotorPawnSimApi*>(sim_api)->getVehicleApi();
}
