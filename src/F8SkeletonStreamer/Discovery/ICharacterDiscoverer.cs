using System;

namespace F8SkeletonStreamer.Discovery
{
    internal interface ICharacterDiscoverer
    {
        event Action<CharacterInfo> CharacterJoined;
        event Action<CharacterInfo> CharacterLeft;
        CharacterInfo[] GetCharacters();
    }
}
