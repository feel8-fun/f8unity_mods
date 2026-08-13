using F8SkeletonStreamer.Sampling;

namespace F8SkeletonStreamer.Protocol
{
    public struct CharacterFrame
    {
        public ulong FrameId;
        public long TimestampMs;
        public int CharacterId;
        public string CharacterName;
        public string ProfileId;
        public string Role;
        public int RoleIndex;
        public string ExporterVersion;
        public BoneSample[] Bones;
        public bool HasAnimationContext;
        public float NormalizedTime;
        public int LayerIndex;
        public string ClipName;
        public string PoseKey;
    }
}
