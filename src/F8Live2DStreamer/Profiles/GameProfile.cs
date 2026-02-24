namespace F8Live2DStreamer.Profiles
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

        // Legacy fields kept for compatibility with copied helper classes.
        public string controllerType = "Animator";
        public string femaleControllerExpr = string.Empty;
        public string maleControllerExpr = string.Empty;
        public string femaleRootsExpr = string.Empty;
        public string maleRootsExpr = string.Empty;
        public int maxFemaleCount = 1;
        public int maxMaleCount = 1;
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

        // Live2D fields.
        public string captureMode = "Auto";
        public string live2dRootsExpr = string.Empty;
        public bool autoDiscoverCubism = true;
        public int maxModelCount = 0;
        public bool activeOnly = true;
        public string drawableNameIncludeRegex = string.Empty;
        public string drawableNameExcludeRegex = string.Empty;
        public float minBoundsExtent = 0.0001f;

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
