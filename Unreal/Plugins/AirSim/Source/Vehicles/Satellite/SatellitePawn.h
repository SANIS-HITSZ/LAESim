#pragma once

#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

#include "AirBlueprintLib.h"
#include "PIPCamera.h"
#include "PawnEvents.h"
#include "common/AirSimSettings.hpp"
#include "common/common_utils/UniqueValueMap.hpp"
#include "vehicles/satellite/api/SatelliteApiBase.hpp"

#include "SatellitePawn.generated.h"

UCLASS(config = Game)
class ASatellitePawn : public APawn
{
    GENERATED_BODY()

public:
    ASatellitePawn();

    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void NotifyHit(class UPrimitiveComponent* MyComp, class AActor* Other, class UPrimitiveComponent* OtherComp, bool bSelfMoved, FVector HitLocation,
                           FVector HitNormal, FVector NormalImpulse, const FHitResult& Hit) override;

    void initializeForBeginPlay();
    const common_utils::UniqueValueMap<std::string, APIPCamera*> getCameras() const;
    PawnEvents* getPawnEvents()
    {
        return &pawn_events_;
    }
    const msr::airlib::SatelliteApiBase::SatelliteControls& getKeyBoardControls() const
    {
        return keyboard_controls_;
    }

private:
    UStaticMeshComponent* addBoxPart(const FName& name, const FVector& relative_location, const FVector& relative_scale);

private:
    UPROPERTY()
    UClass* pip_camera_class_;

    PawnEvents pawn_events_;
    msr::airlib::SatelliteApiBase::SatelliteControls keyboard_controls_;

    UPROPERTY()
    USceneComponent* root_component_;

    UPROPERTY()
    UStaticMesh* satellite_mesh_;

    UPROPERTY()
    UStaticMesh* cube_mesh_;

    UPROPERTY()
    UStaticMeshComponent* body_;
    UPROPERTY()
    UStaticMeshComponent* left_panel_;
    UPROPERTY()
    UStaticMeshComponent* right_panel_;
    UPROPERTY()
    UStaticMeshComponent* antenna_;
    UPROPERTY()
    UStaticMeshComponent* dish_;

    UPROPERTY()
    USceneComponent* camera_front_center_base_;
    UPROPERTY()
    USceneComponent* camera_front_left_base_;
    UPROPERTY()
    USceneComponent* camera_front_right_base_;
    UPROPERTY()
    USceneComponent* camera_driver_base_;
    UPROPERTY()
    USceneComponent* camera_back_center_base_;

    UPROPERTY()
    APIPCamera* camera_front_center_;
    UPROPERTY()
    APIPCamera* camera_front_left_;
    UPROPERTY()
    APIPCamera* camera_front_right_;
    UPROPERTY()
    APIPCamera* camera_driver_;
    UPROPERTY()
    APIPCamera* camera_back_center_;
};
