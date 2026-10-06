using UnrealBuildTool;
using System.Collections.Generic;

public class WirelessCityFactoryEditorTarget : TargetRules
{
    public WirelessCityFactoryEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V2;
        ExtraModuleNames.AddRange(new string[] { "WirelessCityFactory" });
    }
}
