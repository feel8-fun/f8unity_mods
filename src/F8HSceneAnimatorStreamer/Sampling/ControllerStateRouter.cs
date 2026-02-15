using F8HSceneAnimatorStreamer.Discovery;
using F8HSceneAnimatorStreamer.Profiles;
using UnityEngine;
using CharacterModel = F8HSceneAnimatorStreamer.Discovery.CharacterInfo;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal sealed class ControllerStateRouter : MonoBehaviour, IControllerStateReader
    {
        private ProfileResolver _resolver;
        private AnimatorStateReader _animatorReader;
        private AnimationStateReader _animationReader;

        private void Awake()
        {
            _resolver = GetComponent<ProfileResolver>();
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
                return _animationReader != null && _animationReader.TryGetState(character, out state);
            }
            return _animatorReader != null && _animatorReader.TryGetState(character, out state);
        }
    }
}
