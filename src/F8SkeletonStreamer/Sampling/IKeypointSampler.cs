using F8SkeletonStreamer.Discovery;

namespace F8SkeletonStreamer.Sampling
{
    internal interface IKeypointSampler
    {
        BoneSample[] SampleRealtime(CharacterInfo character);
    }
}
