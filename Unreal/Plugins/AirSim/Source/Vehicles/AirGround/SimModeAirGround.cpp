#include "SimModeAirGround.h"

#include "AirBlueprintLib.h"
#include "Vehicles/Boat/BoatPawnSimApi.h"
#include "Vehicles/Car/CarPawnSimApi.h"
#include "Vehicles/Multirotor/MultirotorPawnSimApi.h"
#include "Vehicles/Satellite/SatellitePawnSimApi.h"
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
        static_cast<uint16_t>(getSettings().api_port_multirotor),
        static_cast<uint16_t>(getSettings().api_port_boat),
        static_cast<uint16_t>(getSettings().api_port_satellite)));
#endif
}

void ASimModeAirGround::getExistingVehiclePawns(TArray<AActor*>& pawns) const
{
    TArray<AActor*> drone_pawns;
    TArray<AActor*> car_pawns;
    TArray<AActor*> boat_pawns;
    TArray<AActor*> satellite_pawns;
    UAirBlueprintLib::FindAllActor<AFlyingPawn>(this, drone_pawns);
    UAirBlueprintLib::FindAllActor<ACarPawn>(this, car_pawns);
    UAirBlueprintLib::FindAllActor<ABoatPawn>(this, boat_pawns);
    UAirBlueprintLib::FindAllActor<ASatellitePawn>(this, satellite_pawns);

    pawns.Append(drone_pawns);
    pawns.Append(car_pawns);
    pawns.Append(boat_pawns);
    pawns.Append(satellite_pawns);
}

bool ASimModeAirGround::isVehicleTypeSupported(const std::string& vehicle_type) const
{
    return AirSimSettings::isMultirotor(vehicle_type) || AirSimSettings::isCar(vehicle_type) ||
           AirSimSettings::isBoat(vehicle_type) || AirSimSettings::isSatellite(vehicle_type);
}

std::string ASimModeAirGround::getVehiclePawnPathName(const AirSimSettings::VehicleSetting& vehicle_setting) const
{
    if (!vehicle_setting.pawn_path.empty())
        return vehicle_setting.pawn_path;

    if (AirSimSettings::isCar(vehicle_setting.vehicle_type))
        return "DefaultCar";
    if (AirSimSettings::isBoat(vehicle_setting.vehicle_type))
        return "DefaultBoat";
    if (AirSimSettings::isSatellite(vehicle_setting.vehicle_type))
        return "DefaultSatellite";
    return "DefaultQuadrotor";
}

PawnEvents* ASimModeAirGround::getVehiclePawnEvents(APawn* pawn) const
{
    if (auto* satellite_pawn = Cast<ASatellitePawn>(pawn))
        return satellite_pawn->getPawnEvents();
    if (auto* boat_pawn = Cast<ABoatPawn>(pawn))
        return boat_pawn->getPawnEvents();
    if (auto* car_pawn = Cast<ACarPawn>(pawn))
        return car_pawn->getPawnEvents();

    return static_cast<AFlyingPawn*>(pawn)->getPawnEvents();
}

const common_utils::UniqueValueMap<std::string, APIPCamera*> ASimModeAirGround::getVehiclePawnCameras(APawn* pawn) const
{
    if (auto* satellite_pawn = Cast<ASatellitePawn>(pawn))
        return satellite_pawn->getCameras();
    if (auto* boat_pawn = Cast<ABoatPawn>(pawn))
        return boat_pawn->getCameras();
    if (auto* car_pawn = Cast<ACarPawn>(pawn))
        return car_pawn->getCameras();

    return static_cast<AFlyingPawn*>(pawn)->getCameras();
}

void ASimModeAirGround::initializeVehiclePawn(APawn* pawn)
{
    if (auto* satellite_pawn = Cast<ASatellitePawn>(pawn)) {
        satellite_pawn->initializeForBeginPlay();
        return;
    }
    if (auto* boat_pawn = Cast<ABoatPawn>(pawn)) {
        boat_pawn->initializeForBeginPlay();
        return;
    }
    if (auto* car_pawn = Cast<ACarPawn>(pawn)) {
        car_pawn->initializeForBeginPlay(getSettings().engine_sound);
        return;
    }

    static_cast<AFlyingPawn*>(pawn)->initializeForBeginPlay();
}

std::unique_ptr<PawnSimApi> ASimModeAirGround::createVehicleSimApi(
    const PawnSimApi::Params& pawn_sim_api_params) const
{
    if (Cast<ASatellitePawn>(pawn_sim_api_params.pawn) != nullptr) {
        auto* vehicle_pawn = static_cast<ASatellitePawn*>(pawn_sim_api_params.pawn);
        auto vehicle_sim_api = std::unique_ptr<PawnSimApi>(new SatellitePawnSimApi(
            pawn_sim_api_params, vehicle_pawn->getKeyBoardControls()));
        vehicle_sim_api->initialize();
        vehicle_sim_api->reset();
        return vehicle_sim_api;
    }

    if (Cast<ABoatPawn>(pawn_sim_api_params.pawn) != nullptr) {
        auto* vehicle_pawn = static_cast<ABoatPawn*>(pawn_sim_api_params.pawn);
        auto vehicle_sim_api = std::unique_ptr<PawnSimApi>(new BoatPawnSimApi(
            pawn_sim_api_params, vehicle_pawn->getKeyBoardControls()));
        vehicle_sim_api->initialize();
        vehicle_sim_api->reset();
        return vehicle_sim_api;
    }

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
    if (Cast<ASatellitePawn>(pawn_sim_api_params.pawn) != nullptr)
        return static_cast<const SatellitePawnSimApi*>(sim_api)->getVehicleApi();

    if (Cast<ABoatPawn>(pawn_sim_api_params.pawn) != nullptr)
        return static_cast<const BoatPawnSimApi*>(sim_api)->getVehicleApi();

    if (Cast<ACarPawn>(pawn_sim_api_params.pawn) != nullptr)
        return static_cast<const CarPawnSimApi*>(sim_api)->getVehicleApi();

    return static_cast<const MultirotorPawnSimApi*>(sim_api)->getVehicleApi();
}

APawn* ASimModeAirGround::createVehiclePawn(const AirSimSettings::VehicleSetting& vehicle_setting)
{
    if ((!AirSimSettings::isBoat(vehicle_setting.vehicle_type) &&
         !AirSimSettings::isSatellite(vehicle_setting.vehicle_type)) ||
        !vehicle_setting.pawn_path.empty())
        return ASimModeWorldBase::createVehiclePawn(vehicle_setting);

    const FTransform uu_origin = getGlobalNedTransform().getGlobalTransform();

    FVector spawn_position = uu_origin.GetLocation();
    if (!msr::airlib::VectorMath::hasNan(vehicle_setting.position))
        spawn_position = getGlobalNedTransform().fromGlobalNed(vehicle_setting.position);

    FRotator spawn_rotation = toFRotator(vehicle_setting.rotation, uu_origin.Rotator());

    FActorSpawnParameters pawn_spawn_params;
    pawn_spawn_params.Name = FName(vehicle_setting.vehicle_name.c_str());
    pawn_spawn_params.SpawnCollisionHandlingOverride =
        ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

    APawn* spawned_pawn = nullptr;
    if (AirSimSettings::isSatellite(vehicle_setting.vehicle_type)) {
        spawned_pawn = this->GetWorld()->SpawnActor<ASatellitePawn>(
            spawn_position, spawn_rotation, pawn_spawn_params);
    }
    else {
        spawned_pawn = this->GetWorld()->SpawnActor<ABoatPawn>(
            spawn_position, spawn_rotation, pawn_spawn_params);
    }

    return spawned_pawn;
}
