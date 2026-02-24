using System;
using System.Collections.Generic;
using System.Linq;

namespace F8SkeletonStreamer.Triggering
{
    internal static class KnownHookProfiles
    {
        private static readonly HookProfile[] Profiles =
        {
            new HookProfile
            {
                ProcessNames = new[] { "HoneySelect2", "HoneySelect2VR", "AI-Syoujyo" },
                StartMethods = new[] { "HScene, Assembly-CSharp:SetStartVoice" },
                EndMethods = new[] { "HScene, Assembly-CSharp:EndProc" }
            },
            new HookProfile
            {
                ProcessNames = new[] { "Koikatu", "Koikatsu Party", "KoikatuSunshine" },
                StartMethods = new[] { "HFlag, Assembly-CSharp:Start" },
                EndMethods = new[]
                {
                    "HSprite, Assembly-CSharp:OnClickHSceneEnd",
                    "HSprite, Assembly-CSharp:OnClickTrespassing"
                }
            },
            new HookProfile
            {
                ProcessNames = new[] { "RoomGirl" },
                StartMethods = new[] { "HScene, Assembly-CSharp:Start" },
                EndMethods = new[] { "HScene, Assembly-CSharp:OnDestroy" }
            }
        };

        public static HookProfile FindByProcess(string processName)
        {
            if (string.IsNullOrEmpty(processName))
            {
                return null;
            }
            return Profiles.FirstOrDefault(profile =>
                profile.ProcessNames.Any(name =>
                    string.Equals(name, processName, StringComparison.OrdinalIgnoreCase)));
        }

        public static string[] ParseMethodList(string source)
        {
            if (string.IsNullOrEmpty(source))
            {
                return new string[0];
            }
            return source.Split(new[] { ';' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(token => token.Trim())
                .Where(token => token.Length > 0)
                .Distinct()
                .ToArray();
        }

        public static string[] MergeMethods(string[] primary, string[] fallback)
        {
            var result = new List<string>();
            if (primary != null)
            {
                result.AddRange(primary.Where(item => !string.IsNullOrEmpty(item)));
            }
            if (result.Count > 0)
            {
                return result.Distinct().ToArray();
            }
            if (fallback == null)
            {
                return new string[0];
            }
            return fallback.Where(item => !string.IsNullOrEmpty(item)).Distinct().ToArray();
        }
    }
}
