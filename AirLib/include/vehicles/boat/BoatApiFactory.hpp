#ifndef msr_airlib_vehicles_BoatApiFactory_hpp
#define msr_airlib_vehicles_BoatApiFactory_hpp

#include "vehicles/boat/firmwares/simple_boat/SimpleBoatApi.hpp"

namespace msr
{
namespace airlib
{
    class BoatApiFactory
    {
    public:
        static std::unique_ptr<BoatApiBase> createApi(const AirSimSettings::VehicleSetting* vehicle_setting,
                                                      std::shared_ptr<SensorFactory> sensor_factory,
                                                      const Kinematics::State& state, const Environment& environment)
        {
            unused(vehicle_setting);
            return std::unique_ptr<BoatApiBase>(new SimpleBoatApi(vehicle_setting, sensor_factory, state, environment));
        }
    };
}
} //namespace

#endif
