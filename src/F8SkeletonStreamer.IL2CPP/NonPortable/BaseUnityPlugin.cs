using BepInEx.Unity.IL2CPP;
using HarmonyLib;

namespace F8SkeletonStreamer.NonPortable
{
    public class BaseUnityPlugin : BasePlugin
    {
        protected BepInEx.Logging.ManualLogSource Logger
        {
            get { return Log; }
        }

        public override void Load()
        {
            Traverse.Create(this).Method("Start").GetValue();
        }
    }
}
