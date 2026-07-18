#ifndef msr_airlib_vehicles_SatelliteApiFactory_hpp
#define msr_airlib_vehicles_SatelliteApiFactory_hpp

#include "vehicles/satellite/firmwares/simple_satellite/SimpleSatelliteApi.hpp"

namespace msr
{
namespace airlib
{
    class SatelliteApiFactory
    {
    public:
        static std::unique_ptr<SatelliteApiBase> createApi(const AirSimSettings::VehicleSetting* vehicle_setting,
                                                      std::shared_ptr<SensorFactory> sensor_factory,
                                                      const Kinematics::State& state, const Environment& environment)
        {
            unused(vehicle_setting);
            return std::unique_ptr<SatelliteApiBase>(new SimpleSatelliteApi(vehicle_setting, sensor_factory, state, environment));
        }
    };
}
} //namespace

#endif
