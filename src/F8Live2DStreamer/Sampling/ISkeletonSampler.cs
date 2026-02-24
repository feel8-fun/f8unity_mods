using F8Live2DStreamer.Discovery;

namespace F8Live2DStreamer.Sampling
{
    internal interface ISkeletonSampler
    {
        BoneSample[] Sample(CharacterInfo character, bool includeInactive);
    }
}
