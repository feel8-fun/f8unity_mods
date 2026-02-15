using System.IO;
using LitJson;

namespace F8HSceneAnimatorStreamer.Profiles
{
    internal sealed class ProfileLoader
    {
        public GameProfile LoadProfile(string profileFilePath)
        {
            if (string.IsNullOrEmpty(profileFilePath) || !File.Exists(profileFilePath))
            {
                return null;
            }

            try
            {
                string json = File.ReadAllText(profileFilePath);
                GameProfile profile = JsonMapper.ToObject<GameProfile>(json);
                if (profile == null || string.IsNullOrEmpty(profile.id))
                {
                    return null;
                }

                return profile;
            }
            catch
            {
                return null;
            }
        }
    }
}
