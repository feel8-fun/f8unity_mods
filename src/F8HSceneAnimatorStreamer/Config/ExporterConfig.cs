using BepInEx.Configuration;

namespace F8HSceneAnimatorStreamer.Config
{
    internal static class ExporterConfig
    {
        private static ConfigFile _configFile;
        public static string ConfigPath { get; private set; }

        public static ConfigEntry<string> SkeletonHost { get; private set; }
        public static ConfigEntry<int> SkeletonPort { get; private set; }
        public static ConfigEntry<int> MaxUdpPayloadBytes { get; private set; }

        public static ConfigEntry<int> TargetFps { get; private set; }
        public static ConfigEntry<string> PoseKeyStrategy { get; private set; }

        public static void Initialize(F8HSceneAnimatorStreamer.NonPortable.BaseUnityPlugin plugin)
        {
            _configFile = plugin.Config;
            ConfigPath = plugin.Config.ConfigFilePath;

            const string network = "Network";
            SkeletonHost = plugin.Config.Bind(network, "SkeletonHost", "127.0.0.1",
                "Destination host for hook-only skeleton UDP packets.");
            SkeletonPort = plugin.Config.Bind(network, "SkeletonPort", 39540,
                "Destination port for hook-only skeleton UDP packets.");
            MaxUdpPayloadBytes = plugin.Config.Bind(network, "MaxUdpPayloadBytes", 1200,
                "Maximum UDP datagram payload size. Packet chunking is applied above this limit.");

            const string capture = "Capture";
            TargetFps = plugin.Config.Bind(capture, "TargetFps", 60,
                "Target sampling frame rate for hook-active sessions.");
            PoseKeyStrategy = plugin.Config.Bind(capture, "PoseKeyStrategy", "clip_then_statehash",
                "Pose key naming strategy identifier.");
        }

        public static void Reload()
        {
            if (_configFile != null)
            {
                _configFile.Reload();
            }
        }
    }
}
