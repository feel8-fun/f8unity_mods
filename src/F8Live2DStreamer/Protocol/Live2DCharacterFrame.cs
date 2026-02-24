using F8Live2DStreamer.Sampling;

namespace F8Live2DStreamer.Protocol
{
    public struct Live2DCharacterFrame
    {
        public ulong FrameId;
        public long TimestampMs;
        public int CharacterId;
        public string CharacterName;
        public DrawableSample[] Drawables;
    }
}
