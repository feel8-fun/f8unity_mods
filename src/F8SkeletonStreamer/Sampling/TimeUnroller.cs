namespace F8SkeletonStreamer.Sampling
{
    internal sealed class TimeUnroller
    {
        private float _last;
        private int _offset;
        private bool _initialized;

        public float ToMonotonic(float value)
        {
            if (!_initialized)
            {
                _initialized = true;
                _last = value;
                return value;
            }

            if (value < _last)
            {
                _offset += (int)System.Math.Ceiling(_last - value);
            }

            _last = value;
            return value + _offset;
        }
    }
}
