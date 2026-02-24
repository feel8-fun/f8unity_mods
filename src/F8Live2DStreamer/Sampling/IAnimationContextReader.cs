using F8Live2DStreamer.Discovery;

namespace F8Live2DStreamer.Sampling
{
    internal interface IAnimationContextReader
    {
        AnimatorLayerState[] ReadLayers(CharacterInfo character);
    }
}
