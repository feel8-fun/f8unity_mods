using F8SkeletonStreamer.Discovery;

namespace F8SkeletonStreamer.Sampling
{
    internal interface ISkeletonSampler
    {
        BoneSample[] Sample(CharacterInfo character, bool includeInactive);
    }
}
