using F8HSceneAnimatorStreamer.Discovery;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal interface IKeypointSampler
    {
        BoneSample[] SampleRealtime(CharacterInfo character);
    }
}
