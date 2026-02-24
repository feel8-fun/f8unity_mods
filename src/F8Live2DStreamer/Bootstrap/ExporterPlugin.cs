using BepInEx;
using F8Live2DStreamer.Config;
using F8Live2DStreamer.Discovery;
using F8Live2DStreamer.NonPortable;
using F8Live2DStreamer.Profiles;
using F8Live2DStreamer.Sampling;
using F8Live2DStreamer.Triggering;

namespace F8Live2DStreamer.Bootstrap
{
    [BepInPlugin("com.feel8.f8-live2d-streamer",
        "F8 Live2D Streamer", "0.1.0")]
    public sealed class ExporterPlugin : F8Live2DStreamer.NonPortable.BaseUnityPlugin
    {
        private void Start()
        {
            Globals.Initialize(Logger);
            ExporterConfig.Initialize(this);
            if (Globals.ManagerObject.GetComponent<ExporterRuntime>() != null)
            {
                Logger.LogWarning("F8Live2DStreamer runtime already exists, skipping.");
                return;
            }

            Globals.ManagerObject.AddComponent<ProfileResolver>();
            Globals.ManagerObject.AddComponent<HookTriggerSource>();
            Globals.ManagerObject.AddComponent<Live2DCharacterProvider>();
            Globals.ManagerObject.AddComponent<Live2DDrawableSampler>();
            Globals.ManagerObject.AddComponent<ExporterRuntime>();
        }
    }
}
