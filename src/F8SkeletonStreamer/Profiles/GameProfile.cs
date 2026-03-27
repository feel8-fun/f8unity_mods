namespace F8SkeletonStreamer.Profiles
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
        public string femaleControllerExpr = string.Empty;
        public string maleControllerExpr = string.Empty;
        public string femaleRootsExpr = string.Empty;
        public string maleRootsExpr = string.Empty;
        public int maxFemaleCount = 1;
        public int maxMaleCount = 1;
        public string captureMode = "Auto";
        public bool activeOnly = true;
        public bool useRegex = true;
        public int poseLayer = 0;
        public string poseLayerName = string.Empty;
        public bool rewindUnloop = true;
        public string customPoseExpr = string.Empty;
        public string customNormalizedTimeExpr = string.Empty;
        public string customSpeedExpr = string.Empty;
        public string customLengthExpr = string.Empty;
        public bool debugDumpFullHierarchy = false;
        public float autoEndOnNoCharactersSeconds = 0f;
        public KeypointBinding[] keypoints = new KeypointBinding[0];

        public ControllerType GetControllerType()
        {
            return controllerType == "Animation" ? ControllerType.Animation : ControllerType.Animator;
        }

        public CaptureMode GetCaptureMode()
        {
            if (string.Equals(captureMode, "HookOnly", System.StringComparison.OrdinalIgnoreCase))
            {
                return CaptureMode.HookOnly;
            }
            if (string.Equals(captureMode, "AlwaysOn", System.StringComparison.OrdinalIgnoreCase))
            {
                return CaptureMode.AlwaysOn;
            }
            return CaptureMode.Auto;
        }
    }
}
