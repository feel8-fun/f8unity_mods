namespace F8Live2DStreamer.Triggering
{
    internal sealed class HookProfile
    {
        public string[] ProcessNames;
        public string[] StartMethods;
        public string[] EndMethods;
        public string[] ObserveMethods = new string[0];
    }
}
