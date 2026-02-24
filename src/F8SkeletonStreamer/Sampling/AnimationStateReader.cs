using System;
using System.Collections.Generic;
using F8SkeletonStreamer.Discovery;
using F8SkeletonStreamer.Profiles;
using UnityEngine;
using CharacterModel = F8SkeletonStreamer.Discovery.CharacterInfo;

namespace F8SkeletonStreamer.Sampling
{
    internal sealed class AnimationStateReader : MonoBehaviour, IControllerStateReader
    {
        private readonly Dictionary<string, TimeUnroller> _unrollers =
            new Dictionary<string, TimeUnroller>(StringComparer.OrdinalIgnoreCase);

        private ProfileResolver _resolver;

        private void Awake()
        {
            _resolver = GetComponent<ProfileResolver>();
        }

        public bool TryGetState(CharacterModel character, out ControllerState state)
        {
            state = default(ControllerState);
            if (character == null || character.Animation == null)
            {
                return false;
            }

            Animation animation = character.Animation;
            AnimationState active = null;
            foreach (AnimationState candidate in animation)
            {
                if (animation.IsPlaying(candidate.name))
                {
                    active = candidate;
                    break;
                }
            }

            if (active == null)
            {
                return false;
            }

            GameProfile profile = _resolver != null ? _resolver.ActiveProfile : null;
            string poseKey = active.name ?? "animation";
            float normalized = active.length > 0.0001f ? active.time / active.length : 0f;
            if (profile != null && profile.rewindUnloop)
            {
                normalized = GetUnroller(character.CharacterId, poseKey).ToMonotonic(normalized);
            }

            state = new ControllerState
            {
                PoseKey = poseKey,
                NormalizedTime = normalized,
                Length = active.length,
                Speed = active.speed,
                ClipName = active.name,
                LayerIndex = 0
            };
            return true;
        }

        private TimeUnroller GetUnroller(int characterId, string poseKey)
        {
            string key = characterId + "|" + poseKey;
            TimeUnroller unroller;
            if (!_unrollers.TryGetValue(key, out unroller))
            {
                unroller = new TimeUnroller();
                _unrollers[key] = unroller;
            }
            return unroller;
        }
    }
}
