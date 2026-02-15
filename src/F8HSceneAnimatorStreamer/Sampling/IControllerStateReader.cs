using F8HSceneAnimatorStreamer.Discovery;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal interface IControllerStateReader
    {
        bool TryGetState(CharacterInfo character, out ControllerState state);
    }
}
