namespace F8Live2DStreamer.Triggering
{
    public sealed class TriggerSignal
    {
        public TriggerEventType Type;
        public string Source;
        public string Method;
        public string SceneName;
        public int CharacterId;
        public string CharacterName;
        public string PoseKey;
        public string Detail;
        public object HookInstance;
    }
}
