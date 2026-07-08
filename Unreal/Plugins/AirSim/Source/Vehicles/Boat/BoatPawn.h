#pragma once

#include "CoreMinimal.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/ConstructorHelpers.h"

#include "AirBlueprintLib.h"
#include "PIPCamera.h"
#include "PawnEvents.h"
#include "common/AirSimSettings.hpp"
#include "common/common_utils/UniqueValueMap.hpp"
#include "vehicles/boat/api/BoatApiBase.hpp"

#include "BoatPawn.generated.h"

UCLASS(config = Game)
class ABoatPawn : public APawn
{
    GENERATED_BODY()

public:
    ABoatPawn();

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
    const msr::airlib::BoatApiBase::BoatControls& getKeyBoardControls() const
    {
        return keyboard_controls_;
    }

private:
    UStaticMeshComponent* addBoxPart(const FName& name, const FVector& relative_location, const FVector& relative_scale);

private:
    UPROPERTY()
    UClass* pip_camera_class_;

    PawnEvents pawn_events_;
    msr::airlib::BoatApiBase::BoatControls keyboard_controls_;

    UPROPERTY()
    USceneComponent* root_component_;

    UPROPERTY()
    UStaticMesh* boat_mesh_;

    UPROPERTY()
    UStaticMesh* cube_mesh_;

    UPROPERTY()
    UStaticMeshComponent* hull_;
    UPROPERTY()
    UStaticMeshComponent* deck_;
    UPROPERTY()
    UStaticMeshComponent* bridge_;
    UPROPERTY()
    UStaticMeshComponent* mast_;
    UPROPERTY()
    UStaticMeshComponent* bow_turret_;
    UPROPERTY()
    UStaticMeshComponent* bow_barrel_;
    UPROPERTY()
    UStaticMeshComponent* stern_turret_;
    UPROPERTY()
    UStaticMeshComponent* stern_barrel_;

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
