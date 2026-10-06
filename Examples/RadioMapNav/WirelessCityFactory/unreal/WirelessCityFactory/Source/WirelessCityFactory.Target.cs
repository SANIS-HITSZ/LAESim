using UnrealBuildTool;
using System.Collections.Generic;

public class WirelessCityFactoryTarget : TargetRules
{
    public WirelessCityFactoryTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V2;
        ExtraModuleNames.AddRange(new string[] { "WirelessCityFactory" });
    }
}
