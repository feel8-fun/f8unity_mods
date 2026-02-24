using F8SkeletonStreamer.Discovery;

namespace F8SkeletonStreamer.Sampling
{
    internal interface IControllerStateReader
    {
        bool TryGetState(CharacterInfo character, out ControllerState state);
    }
}
