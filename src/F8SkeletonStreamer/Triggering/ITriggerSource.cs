using System;

namespace F8SkeletonStreamer.Triggering
{
    internal interface ITriggerSource
    {
        event Action<TriggerSignal> OnSignal;
    }
}
