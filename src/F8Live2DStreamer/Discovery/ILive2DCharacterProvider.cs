namespace F8Live2DStreamer.Discovery
{
    internal interface ILive2DCharacterProvider
    {
        bool HasActiveSession { get; }
        object ActiveHookInstance { get; }
        Live2DCharacterInfo[] GetActiveCharacters();
        void StartSession(object hookInstance, string hookMethod);
        void EndSession(string hookMethod);
    }
}
