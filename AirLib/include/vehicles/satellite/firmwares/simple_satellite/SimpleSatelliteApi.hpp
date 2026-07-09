#ifndef msr_airlib_vehicles_SimpleSatelliteApi_hpp
#define msr_airlib_vehicles_SimpleSatelliteApi_hpp

#include "vehicles/satellite/api/SatelliteApiBase.hpp"

namespace msr
{
namespace airlib
{
    class SimpleSatelliteApi : public SatelliteApiBase
    {
    public:
        SimpleSatelliteApi(const AirSimSettings::VehicleSetting* vehicle_setting,
                      std::shared_ptr<SensorFactory> sensor_factory,
                      const Kinematics::State& state, const Environment& environment)
            : SatelliteApiBase(vehicle_setting, sensor_factory, state, environment), home_geopoint_(environment.getHomeGeoPoint())
        {
        }

        virtual void enableApiControl(bool is_enabled) override
        {
            if (api_control_enabled_ != is_enabled) {
                controls_ = SatelliteControls();
                api_control_enabled_ = is_enabled;
            }
        }

        virtual bool isApiControlEnabled() const override
        {
            return api_control_enabled_;
        }

        virtual bool armDisarm(bool arm) override
        {
            unused(arm);
            return true;
        }

        virtual GeoPoint getHomeGeoPoint() const override
        {
            return home_geopoint_;
        }

        virtual void setSatelliteControls(const SatelliteControls& controls) override
        {
            controls_ = controls;
        }

        virtual void updateSatelliteState(const SatelliteState& state) override
        {
            state_ = state;
        }

        virtual const SatelliteState& getSatelliteState() const override
        {
            return state_;
        }

        virtual const SatelliteControls& getSatelliteControls() const override
        {
            return controls_;
        }

    protected:
        virtual void resetImplementation() override
        {
            SatelliteApiBase::resetImplementation();
            controls_ = SatelliteControls();
            state_ = SatelliteState();
        }

    private:
        bool api_control_enabled_ = false;
        GeoPoint home_geopoint_;
        SatelliteControls controls_;
        SatelliteState state_;
    };
}
} //namespace

#endif
