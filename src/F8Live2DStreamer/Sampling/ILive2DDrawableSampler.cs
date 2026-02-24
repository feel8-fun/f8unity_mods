using F8Live2DStreamer.Discovery;
using F8Live2DStreamer.Profiles;

namespace F8Live2DStreamer.Sampling
{
    internal interface ILive2DDrawableSampler
    {
        DrawableSample[] Sample(Live2DCharacterInfo character, GameProfile profile);
    }
}
