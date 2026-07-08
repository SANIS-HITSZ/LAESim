#ifndef msr_airlib_vehicles_SimpleBoatApi_hpp
#define msr_airlib_vehicles_SimpleBoatApi_hpp

#include "vehicles/boat/api/BoatApiBase.hpp"

namespace msr
{
namespace airlib
{
    class SimpleBoatApi : public BoatApiBase
    {
    public:
        SimpleBoatApi(const AirSimSettings::VehicleSetting* vehicle_setting,
                      std::shared_ptr<SensorFactory> sensor_factory,
                      const Kinematics::State& state, const Environment& environment)
            : BoatApiBase(vehicle_setting, sensor_factory, state, environment), home_geopoint_(environment.getHomeGeoPoint())
        {
        }

        virtual void enableApiControl(bool is_enabled) override
        {
            if (api_control_enabled_ != is_enabled) {
                controls_ = BoatControls();
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

        virtual void setBoatControls(const BoatControls& controls) override
        {
            controls_ = controls;
        }

        virtual void updateBoatState(const BoatState& state) override
        {
            state_ = state;
        }

        virtual const BoatState& getBoatState() const override
        {
            return state_;
        }

        virtual const BoatControls& getBoatControls() const override
        {
            return controls_;
        }

    protected:
        virtual void resetImplementation() override
        {
            BoatApiBase::resetImplementation();
            controls_ = BoatControls();
            state_ = BoatState();
        }

    private:
        bool api_control_enabled_ = false;
        GeoPoint home_geopoint_;
        BoatControls controls_;
        BoatState state_;
    };
}
} //namespace

#endif
