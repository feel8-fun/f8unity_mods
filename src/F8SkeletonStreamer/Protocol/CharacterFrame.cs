using F8SkeletonStreamer.Sampling;

namespace F8SkeletonStreamer.Protocol
{
    public struct CharacterFrame
    {
        public ulong FrameId;
        public long TimestampMs;
        public int CharacterId;
        public string CharacterName;
        public BoneSample[] Bones;
        public bool HasAnimationContext;
        public float NormalizedTime;
        public int LayerIndex;
        public string ClipName;
        public string PoseKey;
    }
}
