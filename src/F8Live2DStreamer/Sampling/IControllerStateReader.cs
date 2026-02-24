using F8Live2DStreamer.Discovery;

namespace F8Live2DStreamer.Sampling
{
    internal interface IControllerStateReader
    {
        bool TryGetState(CharacterInfo character, out ControllerState state);
    }
}
