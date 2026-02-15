namespace F8HSceneAnimatorStreamer.Profiles
{
    public sealed class KeypointBinding
    {
        public string kind;
        public string pathOrName;
        public bool required = true;

        public KeypointKind GetKind()
        {
            try
            {
                return (KeypointKind)System.Enum.Parse(typeof(KeypointKind),
                    kind ?? string.Empty, true);
            }
            catch
            {
                return KeypointKind.FemaleRoot;
            }
        }
    }
}
