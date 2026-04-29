#ifndef air_MultiPortApiServer_hpp
#define air_MultiPortApiServer_hpp

#include "api/ApiServerBase.hpp"
#include "api/RpcLibServerBase.hpp"
#include "vehicles/car/api/CarRpcLibServer.hpp"
#include "vehicles/multirotor/api/MultirotorRpcLibServer.hpp"

namespace msr
{
namespace airlib
{

    class MultiPortApiServer : public ApiServerBase
    {
    public:
        MultiPortApiServer(ApiProvider* api_provider, const std::string& server_address,
                           uint16_t cv_port, uint16_t car_port, uint16_t multirotor_port)
        {
            cv_server_.reset(new RpcLibServerBase(api_provider, server_address, cv_port));
            car_server_.reset(new CarRpcLibServer(api_provider, server_address, car_port));
            multirotor_server_.reset(new MultirotorRpcLibServer(api_provider, server_address, multirotor_port));
        }

        virtual void start(bool block, std::size_t thread_count) override
        {
            multirotor_server_->start(false, thread_count);
            car_server_->start(false, thread_count);
            cv_server_->start(block, thread_count);
        }

        virtual void stop() override
        {
            if (multirotor_server_)
                multirotor_server_->stop();
            if (car_server_)
                car_server_->stop();
            if (cv_server_)
                cv_server_->stop();
        }

    private:
        std::unique_ptr<ApiServerBase> cv_server_;
        std::unique_ptr<ApiServerBase> car_server_;
        std::unique_ptr<ApiServerBase> multirotor_server_;
    };
}
} //namespace

#endif
