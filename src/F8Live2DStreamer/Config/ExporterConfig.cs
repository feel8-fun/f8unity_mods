using BepInEx.Configuration;

namespace F8Live2DStreamer.Config
{
    internal static class ExporterConfig
    {
        private static ConfigFile _configFile;
        public static string ConfigPath { get; private set; }

        public static ConfigEntry<string> Live2DHost { get; private set; }
        public static ConfigEntry<int> Live2DPort { get; private set; }
        public static ConfigEntry<int> MaxUdpPayloadBytes { get; private set; }

        public static ConfigEntry<int> TargetFps { get; private set; }
        public static ConfigEntry<string> CaptureMode { get; private set; }
        public static ConfigEntry<int> DiscoveryIntervalMs { get; private set; }
        public static ConfigEntry<bool> DebugLogDiscovery { get; private set; }

        public static void Initialize(F8Live2DStreamer.NonPortable.BaseUnityPlugin plugin)
        {
            _configFile = plugin.Config;
            ConfigPath = plugin.Config.ConfigFilePath;

            const string network = "Network";
            Live2DHost = plugin.Config.Bind(network, "Live2DHost", "127.0.0.1",
                "Destination host for Live2D drawable UDP packets.");
            Live2DPort = plugin.Config.Bind(network, "Live2DPort", 39550,
                "Destination port for Live2D drawable UDP packets.");
            MaxUdpPayloadBytes = plugin.Config.Bind(network, "MaxUdpPayloadBytes", 1200,
                "Maximum UDP datagram payload size. Packet chunking is applied above this limit.");

            const string capture = "Capture";
            TargetFps = plugin.Config.Bind(capture, "TargetFps", 60,
                "Target sampling frame rate.");
            CaptureMode = plugin.Config.Bind(capture, "CaptureMode", "Auto",
                "Capture mode: Auto | HookOnly | AlwaysOn.");
            DiscoveryIntervalMs = plugin.Config.Bind(capture, "DiscoveryIntervalMs", 1000,
                "Character discovery refresh interval in milliseconds.");
            DebugLogDiscovery = plugin.Config.Bind(capture, "DebugLogDiscovery", false,
                "Whether discovery emits summary logs.");
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
