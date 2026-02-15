using F8HSceneAnimatorStreamer.Discovery;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal interface IAnimationContextReader
    {
        AnimatorLayerState[] ReadLayers(CharacterInfo character);
    }
}
