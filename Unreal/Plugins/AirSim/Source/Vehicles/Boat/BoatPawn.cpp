#include "BoatPawn.h"

#include "Engine/StaticMesh.h"

ABoatPawn::ABoatPawn()
{
    PrimaryActorTick.bCanEverTick = true;

    static ConstructorHelpers::FClassFinder<APIPCamera> pip_camera_class(TEXT("Blueprint'/AirSim/Blueprints/BP_PIPCamera'"));
    pip_camera_class_ = pip_camera_class.Succeeded() ? pip_camera_class.Class : nullptr;

    static ConstructorHelpers::FObjectFinder<UStaticMesh> boat_mesh(
        TEXT("StaticMesh'/AirSim/Models/Boat/Type_052B_Destroyer_Combined.Type_052B_Destroyer_Combined'"));
    boat_mesh_ = boat_mesh.Succeeded() ? boat_mesh.Object : nullptr;

    static ConstructorHelpers::FObjectFinder<UStaticMesh> cube_mesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
    cube_mesh_ = cube_mesh.Succeeded() ? cube_mesh.Object : nullptr;

    root_component_ = CreateDefaultSubobject<USceneComponent>(TEXT("BoatRoot"));
    RootComponent = root_component_;

    hull_ = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("BoatHull"));
    hull_->SetupAttachment(RootComponent);
    if (boat_mesh_) {
        hull_->SetStaticMesh(boat_mesh_);
        hull_->SetRelativeRotation(FRotator(0.0f, -90.0f, 90.0f));
        hull_->SetRelativeScale3D(FVector(10.0f, 10.0f, 10.0f));
    }
    else if (cube_mesh_) {
        hull_->SetStaticMesh(cube_mesh_);
        hull_->SetRelativeScale3D(FVector(6.0f, 1.15f, 0.35f));
    }
    hull_->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    hull_->SetNotifyRigidBodyCollision(true);

    if (!boat_mesh_) {
        deck_ = addBoxPart(TEXT("BoatDeck"), FVector(0, 0, 55), FVector(4.8f, 0.85f, 0.12f));
        bridge_ = addBoxPart(TEXT("BoatBridge"), FVector(35, 0, 105), FVector(0.9f, 0.55f, 0.55f));
        mast_ = addBoxPart(TEXT("BoatMast"), FVector(40, 0, 185), FVector(0.08f, 0.08f, 0.8f));
        bow_turret_ = addBoxPart(TEXT("BowTurret"), FVector(190, 0, 92), FVector(0.42f, 0.42f, 0.16f));
        bow_barrel_ = addBoxPart(TEXT("BowBarrel"), FVector(235, 0, 102), FVector(0.7f, 0.08f, 0.08f));
        stern_turret_ = addBoxPart(TEXT("SternTurret"), FVector(-180, 0, 92), FVector(0.42f, 0.42f, 0.16f));
        stern_barrel_ = addBoxPart(TEXT("SternBarrel"), FVector(-225, 0, 102), FVector(0.7f, 0.08f, 0.08f));
    }

    camera_front_center_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_center_base_"));
    camera_front_center_base_->SetRelativeLocation(FVector(900, 0, 380));
    camera_front_center_base_->SetupAttachment(RootComponent);

    camera_front_left_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_left_base_"));
    camera_front_left_base_->SetRelativeLocation(FVector(850, -220, 360));
    camera_front_left_base_->SetupAttachment(RootComponent);

    camera_front_right_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_right_base_"));
    camera_front_right_base_->SetRelativeLocation(FVector(850, 220, 360));
    camera_front_right_base_->SetupAttachment(RootComponent);

    camera_driver_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_driver_base_"));
    camera_driver_base_->SetRelativeLocation(FVector(120, 0, 520));
    camera_driver_base_->SetupAttachment(RootComponent);

    camera_back_center_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_back_center_base_"));
    camera_back_center_base_->SetRelativeLocation(FVector(-900, 0, 340));
    camera_back_center_base_->SetupAttachment(RootComponent);
}

UStaticMeshComponent* ABoatPawn::addBoxPart(const FName& name, const FVector& relative_location, const FVector& relative_scale)
{
    UStaticMeshComponent* part = CreateDefaultSubobject<UStaticMeshComponent>(name);
    if (cube_mesh_)
        part->SetStaticMesh(cube_mesh_);
    part->SetRelativeLocation(relative_location);
    part->SetRelativeScale3D(relative_scale);
    part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    part->SetupAttachment(root_component_);
    return part;
}

void ABoatPawn::NotifyHit(class UPrimitiveComponent* MyComp, class AActor* Other, class UPrimitiveComponent* OtherComp, bool bSelfMoved, FVector HitLocation,
                          FVector HitNormal, FVector NormalImpulse, const FHitResult& Hit)
{
    pawn_events_.getCollisionSignal().emit(MyComp, Other, OtherComp, bSelfMoved, HitLocation, HitNormal, NormalImpulse, Hit);
}

void ABoatPawn::initializeForBeginPlay()
{
    FTransform camera_transform(FVector::ZeroVector);
    FActorSpawnParameters camera_spawn_params;
    camera_spawn_params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;

    camera_spawn_params.Name = FName(*(this->GetName() + "_camera_front_center"));
    camera_front_center_ = this->GetWorld()->SpawnActor<APIPCamera>(pip_camera_class_, camera_transform, camera_spawn_params);
    camera_front_center_->AttachToComponent(camera_front_center_base_, FAttachmentTransformRules::KeepRelativeTransform);

    camera_spawn_params.Name = FName(*(this->GetName() + "_camera_front_left"));
    camera_front_left_ = this->GetWorld()->SpawnActor<APIPCamera>(pip_camera_class_, camera_transform, camera_spawn_params);
    camera_front_left_->AttachToComponent(camera_front_left_base_, FAttachmentTransformRules::KeepRelativeTransform);

    camera_spawn_params.Name = FName(*(this->GetName() + "_camera_front_right"));
    camera_front_right_ = this->GetWorld()->SpawnActor<APIPCamera>(pip_camera_class_, camera_transform, camera_spawn_params);
    camera_front_right_->AttachToComponent(camera_front_right_base_, FAttachmentTransformRules::KeepRelativeTransform);

    camera_spawn_params.Name = FName(*(this->GetName() + "_camera_driver"));
    camera_driver_ = this->GetWorld()->SpawnActor<APIPCamera>(pip_camera_class_, camera_transform, camera_spawn_params);
    camera_driver_->AttachToComponent(camera_driver_base_, FAttachmentTransformRules::KeepRelativeTransform);

    camera_spawn_params.Name = FName(*(this->GetName() + "_camera_back_center"));
    camera_back_center_ = this->GetWorld()->SpawnActor<APIPCamera>(pip_camera_class_,
                                                                  FTransform(FRotator(0, -180, 0), FVector::ZeroVector),
                                                                  camera_spawn_params);
    camera_back_center_->AttachToComponent(camera_back_center_base_, FAttachmentTransformRules::KeepRelativeTransform);
}

const common_utils::UniqueValueMap<std::string, APIPCamera*> ABoatPawn::getCameras() const
{
    common_utils::UniqueValueMap<std::string, APIPCamera*> cameras;
    cameras.insert_or_assign("front_center", camera_front_center_);
    cameras.insert_or_assign("front_right", camera_front_right_);
    cameras.insert_or_assign("front_left", camera_front_left_);
    cameras.insert_or_assign("fpv", camera_driver_);
    cameras.insert_or_assign("back_center", camera_back_center_);

    cameras.insert_or_assign("0", camera_front_center_);
    cameras.insert_or_assign("1", camera_front_right_);
    cameras.insert_or_assign("2", camera_front_left_);
    cameras.insert_or_assign("3", camera_driver_);
    cameras.insert_or_assign("4", camera_back_center_);

    cameras.insert_or_assign("", camera_front_center_);

    return cameras;
}

void ABoatPawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    camera_front_center_ = nullptr;
    camera_front_left_ = nullptr;
    camera_front_right_ = nullptr;
    camera_driver_ = nullptr;
    camera_back_center_ = nullptr;

    camera_front_center_base_ = nullptr;
    camera_front_left_base_ = nullptr;
    camera_front_right_base_ = nullptr;
    camera_driver_base_ = nullptr;
    camera_back_center_base_ = nullptr;
}

void ABoatPawn::Tick(float Delta)
{
    Super::Tick(Delta);
    pawn_events_.getPawnTickSignal().emit(Delta);
}

void ABoatPawn::BeginPlay()
{
    Super::BeginPlay();
}
