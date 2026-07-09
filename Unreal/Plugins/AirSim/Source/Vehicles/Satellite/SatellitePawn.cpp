#include "SatellitePawn.h"

#include "Engine/StaticMesh.h"

ASatellitePawn::ASatellitePawn()
{
    PrimaryActorTick.bCanEverTick = true;

    static ConstructorHelpers::FClassFinder<APIPCamera> pip_camera_class(TEXT("Blueprint'/AirSim/Blueprints/BP_PIPCamera'"));
    pip_camera_class_ = pip_camera_class.Succeeded() ? pip_camera_class.Class : nullptr;

    static ConstructorHelpers::FObjectFinder<UStaticMesh> satellite_mesh(
        TEXT("StaticMesh'/AirSim/Models/Satellite/10477_Satellite_v1_L3.10477_Satellite_v1_L3'"));
    satellite_mesh_ = satellite_mesh.Succeeded() ? satellite_mesh.Object : nullptr;

    static ConstructorHelpers::FObjectFinder<UStaticMesh> cube_mesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
    cube_mesh_ = cube_mesh.Succeeded() ? cube_mesh.Object : nullptr;

    root_component_ = CreateDefaultSubobject<USceneComponent>(TEXT("SatelliteRoot"));
    RootComponent = root_component_;

    body_ = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("SatelliteBody"));
    body_->SetupAttachment(RootComponent);
    if (satellite_mesh_) {
        body_->SetStaticMesh(satellite_mesh_);
        body_->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
        body_->SetRelativeScale3D(FVector(1.0f, 1.0f, 1.0f));
    }
    else if (cube_mesh_) {
        body_->SetStaticMesh(cube_mesh_);
        body_->SetRelativeScale3D(FVector(0.7f, 0.7f, 0.7f));
    }
    body_->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    body_->SetNotifyRigidBodyCollision(true);

    if (!satellite_mesh_) {
        left_panel_ = addBoxPart(TEXT("LeftSolarPanel"), FVector(0, -145, 0), FVector(0.08f, 1.9f, 0.55f));
        right_panel_ = addBoxPart(TEXT("RightSolarPanel"), FVector(0, 145, 0), FVector(0.08f, 1.9f, 0.55f));
        antenna_ = addBoxPart(TEXT("SatelliteAntenna"), FVector(0, 0, 95), FVector(0.08f, 0.08f, 0.9f));
        dish_ = addBoxPart(TEXT("SatelliteDish"), FVector(75, 0, -15), FVector(0.55f, 0.55f, 0.08f));
    }

    camera_front_center_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_center_base_"));
    camera_front_center_base_->SetRelativeLocation(FVector(220, 0, 70));
    camera_front_center_base_->SetupAttachment(RootComponent);

    camera_front_left_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_left_base_"));
    camera_front_left_base_->SetRelativeLocation(FVector(180, -80, 60));
    camera_front_left_base_->SetupAttachment(RootComponent);

    camera_front_right_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_front_right_base_"));
    camera_front_right_base_->SetRelativeLocation(FVector(180, 80, 60));
    camera_front_right_base_->SetupAttachment(RootComponent);

    camera_driver_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_driver_base_"));
    camera_driver_base_->SetRelativeLocation(FVector(0, 0, 160));
    camera_driver_base_->SetupAttachment(RootComponent);

    camera_back_center_base_ = CreateDefaultSubobject<USceneComponent>(TEXT("camera_back_center_base_"));
    camera_back_center_base_->SetRelativeLocation(FVector(-220, 0, 70));
    camera_back_center_base_->SetupAttachment(RootComponent);
}

UStaticMeshComponent* ASatellitePawn::addBoxPart(const FName& name, const FVector& relative_location, const FVector& relative_scale)
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

void ASatellitePawn::NotifyHit(class UPrimitiveComponent* MyComp, class AActor* Other, class UPrimitiveComponent* OtherComp, bool bSelfMoved, FVector HitLocation,
                          FVector HitNormal, FVector NormalImpulse, const FHitResult& Hit)
{
    pawn_events_.getCollisionSignal().emit(MyComp, Other, OtherComp, bSelfMoved, HitLocation, HitNormal, NormalImpulse, Hit);
}

void ASatellitePawn::initializeForBeginPlay()
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

const common_utils::UniqueValueMap<std::string, APIPCamera*> ASatellitePawn::getCameras() const
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

void ASatellitePawn::EndPlay(const EEndPlayReason::Type EndPlayReason)
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

void ASatellitePawn::Tick(float Delta)
{
    Super::Tick(Delta);
    pawn_events_.getPawnTickSignal().emit(Delta);
}

void ASatellitePawn::BeginPlay()
{
    Super::BeginPlay();
}
