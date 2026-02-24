using F8SkeletonStreamer.Discovery;

namespace F8SkeletonStreamer.Sampling
{
    internal interface IAnimationContextReader
    {
        AnimatorLayerState[] ReadLayers(CharacterInfo character);
    }
}
