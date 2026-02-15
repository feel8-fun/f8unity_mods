namespace F8HSceneAnimatorStreamer.Discovery
{
    internal interface ICharacterProvider
    {
        void StartSession(object hookInstance, string hookMethod);
        void EndSession(string hookMethod);
        CharacterInfo[] GetActiveCharacters();
        bool HasActiveSession { get; }
        string ActiveProfileId { get; }
    }
}
