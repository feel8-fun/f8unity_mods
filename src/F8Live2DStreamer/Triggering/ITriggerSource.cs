using System;

namespace F8Live2DStreamer.Triggering
{
    internal interface ITriggerSource
    {
        event Action<TriggerSignal> OnSignal;
    }
}
