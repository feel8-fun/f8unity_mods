using System;

namespace F8Live2DStreamer.Discovery
{
    internal interface ICharacterDiscoverer
    {
        event Action<CharacterInfo> CharacterJoined;
        event Action<CharacterInfo> CharacterLeft;
        CharacterInfo[] GetCharacters();
    }
}
