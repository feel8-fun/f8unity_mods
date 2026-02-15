using BepInEx.Unity.IL2CPP;
using HarmonyLib;

namespace UnityRealtimeSkeletonExporter.NonPortable
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
