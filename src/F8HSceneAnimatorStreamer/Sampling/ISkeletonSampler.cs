using F8HSceneAnimatorStreamer.Discovery;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal interface ISkeletonSampler
    {
        BoneSample[] Sample(CharacterInfo character, bool includeInactive);
    }
}
