param(
    [string]$Config = "configs/city_only.yaml"
)

$ErrorActionPreference = "Stop"
py -m wireless_city_factory generate --config $Config

