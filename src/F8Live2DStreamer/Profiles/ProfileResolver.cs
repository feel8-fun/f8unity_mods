using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace F8Live2DStreamer.Profiles
{
    internal sealed class ProfileResolver : MonoBehaviour, IProfileResolver
    {
        private readonly Dictionary<string, GameProfile> _profilesById =
            new Dictionary<string, GameProfile>(StringComparer.OrdinalIgnoreCase);

        public GameProfile ActiveProfile { get; private set; }

        private void Start()
        {
            Reload();
        }

        public GameProfile Resolve(string processName)
        {
            _ = processName;
            return ActiveProfile;
        }

        public void Reload()
        {
            _profilesById.Clear();

            string baseDirectory = Path.GetDirectoryName(typeof(ProfileResolver).Assembly.Location) ?? string.Empty;
            string profileFile = Path.Combine(baseDirectory, "profile.json");
            GameProfile loaded = new ProfileLoader().LoadProfile(profileFile);
            if (loaded != null && !string.IsNullOrEmpty(loaded.id))
            {
                _profilesById[loaded.id] = loaded;
            }

            ActiveProfile = loaded;
        }

        public string ActiveProfileId
        {
            get { return ActiveProfile != null ? ActiveProfile.id : string.Empty; }
        }

        public GameProfile GetById(string profileId)
        {
            if (string.IsNullOrEmpty(profileId))
            {
                return null;
            }

            if (ActiveProfile == null || string.IsNullOrEmpty(ActiveProfile.id))
            {
                return null;
            }

            return string.Equals(ActiveProfile.id, profileId, StringComparison.OrdinalIgnoreCase)
                ? ActiveProfile
                : null;
        }
    }
}
