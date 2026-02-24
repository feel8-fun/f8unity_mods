namespace F8Live2DStreamer.Discovery
{
    internal interface ICharacterProvider
    {
        void StartSession(object hookInstance, string hookMethod);
        void EndSession(string hookMethod);
        CharacterInfo[] GetActiveCharacters();
        object ActiveHookInstance { get; }
        bool HasActiveSession { get; }
        string ActiveProfileId { get; }
    }
}
