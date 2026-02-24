using BepInEx;
using F8SkeletonStreamer.Config;
using F8SkeletonStreamer.Discovery;
using F8SkeletonStreamer.NonPortable;
using F8SkeletonStreamer.Profiles;
using F8SkeletonStreamer.Sampling;
using F8SkeletonStreamer.Triggering;

namespace F8SkeletonStreamer.Bootstrap
{
    [BepInPlugin("com.feel8.f8-skeleton-streamer",
        "F8 Skeleton Streamer", "0.1.0")]
    public sealed class ExporterPlugin : F8SkeletonStreamer.NonPortable.BaseUnityPlugin
    {
        private void Start()
        {
            Globals.Initialize(Logger);
            ExporterConfig.Initialize(this);
            if (Globals.ManagerObject.GetComponent<ExporterRuntime>() != null)
            {
                Logger.LogWarning("F8SkeletonStreamer runtime already exists, skipping.");
                return;
            }

            Globals.ManagerObject.AddComponent<ProfileResolver>();
            Globals.ManagerObject.AddComponent<HookTriggerSource>();
            Globals.ManagerObject.AddComponent<ProfileCharacterProvider>();
            Globals.ManagerObject.AddComponent<KeypointSampler>();
            Globals.ManagerObject.AddComponent<FullSkeletonSampler>();
            Globals.ManagerObject.AddComponent<AnimatorStateReader>();
            Globals.ManagerObject.AddComponent<AnimationStateReader>();
            Globals.ManagerObject.AddComponent<ControllerStateRouter>();
            Globals.ManagerObject.AddComponent<ExporterRuntime>();
        }
    }
}
