namespace F8SkeletonStreamer.Profiles
{
    internal interface IProfileResolver
    {
        GameProfile Resolve(string processName);
        void Reload();
        GameProfile ActiveProfile { get; }
    }
}
