using System.Globalization;
using F8HSceneAnimatorStreamer.Discovery;
using F8HSceneAnimatorStreamer.Profiles;
using UnityEngine;
using CharacterModel = F8HSceneAnimatorStreamer.Discovery.CharacterInfo;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal sealed class ControllerStateRouter : MonoBehaviour, IControllerStateReader
    {
        private readonly ExpressionEvaluator _evaluator = new ExpressionEvaluator();

        private ProfileResolver _resolver;
        private ICharacterProvider _characterProvider;
        private AnimatorStateReader _animatorReader;
        private AnimationStateReader _animationReader;

        private void Awake()
        {
            _resolver = GetComponent<ProfileResolver>();
            _characterProvider = GetComponent<ProfileCharacterProvider>();
            _animatorReader = GetComponent<AnimatorStateReader>();
            _animationReader = GetComponent<AnimationStateReader>();
        }

        public bool TryGetState(CharacterModel character, out ControllerState state)
        {
            state = default(ControllerState);
            GameProfile profile = _resolver != null ? _resolver.ActiveProfile : null;
            ControllerType type = profile != null ? profile.GetControllerType() : ControllerType.Animator;
            if (type == ControllerType.Animation)
            {
                if (_animationReader != null && _animationReader.TryGetState(character, out state))
                {
                    return true;
                }
            }
            else if (_animatorReader != null && _animatorReader.TryGetState(character, out state))
            {
                return true;
            }

            return TryGetCustomState(profile, out state);
        }

        private bool TryGetCustomState(GameProfile profile, out ControllerState state)
        {
            state = default(ControllerState);
            if (profile == null || _characterProvider == null || _characterProvider.ActiveHookInstance == null)
            {
                return false;
            }

            object hookInstance = _characterProvider.ActiveHookInstance;
            string pose = ReadString(hookInstance, profile.customPoseExpr);
            float? normalized = ReadFloat(hookInstance, profile.customNormalizedTimeExpr);
            float? speed = ReadFloat(hookInstance, profile.customSpeedExpr);
            float? length = ReadFloat(hookInstance, profile.customLengthExpr);

            bool hasAny = !string.IsNullOrEmpty(pose) || normalized.HasValue || speed.HasValue || length.HasValue;
            if (!hasAny)
            {
                return false;
            }

            state = new ControllerState
            {
                PoseKey = string.IsNullOrEmpty(pose) ? "custom_pose" : pose,
                ClipName = string.IsNullOrEmpty(pose) ? "custom_clip" : pose,
                NormalizedTime = normalized ?? 0f,
                Speed = speed ?? 1f,
                Length = length ?? 1f,
                LayerIndex = 0
            };
            return true;
        }

        private string ReadString(object hookInstance, string expr)
        {
            if (string.IsNullOrEmpty(expr))
            {
                return string.Empty;
            }

            object[] values = _evaluator.EvaluateObjects(hookInstance, expr);
            if (values == null || values.Length == 0 || values[0] == null)
            {
                return string.Empty;
            }

            return values[0].ToString() ?? string.Empty;
        }

        private float? ReadFloat(object hookInstance, string expr)
        {
            if (string.IsNullOrEmpty(expr))
            {
                return null;
            }

            object[] values = _evaluator.EvaluateObjects(hookInstance, expr);
            if (values == null || values.Length == 0 || values[0] == null)
            {
                return null;
            }

            object value = values[0];
            if (value is float f)
            {
                return f;
            }
            if (value is double d)
            {
                return (float)d;
            }
            if (value is int i)
            {
                return i;
            }
            if (value is long l)
            {
                return l;
            }

            string text = value.ToString();
            if (string.IsNullOrEmpty(text))
            {
                return null;
            }

            if (float.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out float parsed))
            {
                return parsed;
            }
            if (float.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out parsed))
            {
                return parsed;
            }

            return null;
        }
    }
}
