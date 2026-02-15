using BepInEx;
using F8HSceneAnimatorStreamer.Config;
using F8HSceneAnimatorStreamer.Discovery;
using F8HSceneAnimatorStreamer.NonPortable;
using F8HSceneAnimatorStreamer.Profiles;
using F8HSceneAnimatorStreamer.Sampling;
using F8HSceneAnimatorStreamer.Triggering;

namespace F8HSceneAnimatorStreamer.Bootstrap
{
    [BepInPlugin("com.feel8.f8-hscene-animator-streamer",
        "F8 HScene Animator Streamer", "0.1.0")]
    public sealed class ExporterPlugin : F8HSceneAnimatorStreamer.NonPortable.BaseUnityPlugin
    {
        private void Start()
        {
            Globals.Initialize(Logger);
            ExporterConfig.Initialize(this);
            if (Globals.ManagerObject.GetComponent<ExporterRuntime>() != null)
            {
                Logger.LogWarning("F8HSceneAnimatorStreamer runtime already exists, skipping.");
                return;
            }

            Globals.ManagerObject.AddComponent<ProfileResolver>();
            Globals.ManagerObject.AddComponent<HookTriggerSource>();
            Globals.ManagerObject.AddComponent<ProfileCharacterProvider>();
            Globals.ManagerObject.AddComponent<KeypointSampler>();
            Globals.ManagerObject.AddComponent<AnimatorStateReader>();
            Globals.ManagerObject.AddComponent<AnimationStateReader>();
            Globals.ManagerObject.AddComponent<ControllerStateRouter>();
            Globals.ManagerObject.AddComponent<ExporterRuntime>();
        }
    }
}
