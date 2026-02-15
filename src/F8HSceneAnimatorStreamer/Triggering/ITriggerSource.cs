using System;

namespace F8HSceneAnimatorStreamer.Triggering
{
    internal interface ITriggerSource
    {
        event Action<TriggerSignal> OnSignal;
    }
}
