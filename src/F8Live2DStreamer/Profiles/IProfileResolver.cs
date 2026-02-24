namespace F8Live2DStreamer.Profiles
{
    internal interface IProfileResolver
    {
        GameProfile Resolve(string processName);
        void Reload();
        GameProfile ActiveProfile { get; }
    }
}
