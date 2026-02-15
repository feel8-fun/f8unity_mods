namespace F8HSceneAnimatorStreamer.Profiles
{
    public sealed class GameProfile
    {
        public string id;
        public string fullName = string.Empty;
        public string version = string.Empty;
        public string[] processNames = new string[0];
        public string[] hooksStart = new string[0];
        public string[] hooksEnd = new string[0];
        public string[] hooksObserve = new string[0];
        public string controllerType = "Animator";
        public string controllerExpr = string.Empty;
        public string femaleRootsExpr = string.Empty;
        public string malePenisBaseExpr = string.Empty;
        public int maxFemaleCount = 1;
        public bool useRegex = true;
        public int poseLayer = 0;
        public string poseLayerName = string.Empty;
        public bool rewindUnloop = true;
        public KeypointBinding[] keypoints = new KeypointBinding[0];

        public ControllerType GetControllerType()
        {
            return controllerType == "Animation" ? ControllerType.Animation : ControllerType.Animator;
        }
    }
}
