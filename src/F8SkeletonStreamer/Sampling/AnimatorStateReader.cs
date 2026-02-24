using System;
using System.Collections.Generic;
using F8SkeletonStreamer.Discovery;
using F8SkeletonStreamer.Profiles;
using UnityEngine;
using CharacterModel = F8SkeletonStreamer.Discovery.CharacterInfo;

namespace F8SkeletonStreamer.Sampling
{
    internal sealed class AnimatorStateReader : MonoBehaviour, IControllerStateReader
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
            if (character == null || character.Animator == null)
            {
                return false;
            }

            GameProfile profile = _resolver != null ? _resolver.ActiveProfile : null;
            Animator animator = character.Animator;
            int layer = ResolveLayer(animator, profile);
            if (layer < 0 || layer >= animator.layerCount)
            {
                layer = 0;
            }

            AnimatorStateInfo info = animator.GetCurrentAnimatorStateInfo(layer);
            AnimatorClipInfo[] clips = animator.GetCurrentAnimatorClipInfo(layer);
            string clipName = string.Empty;
            float clipWeight = float.MinValue;
            for (int i = 0; i < clips.Length; i++)
            {
                AnimatorClipInfo clipInfo = clips[i];
                if (clipInfo.clip == null || clipInfo.weight < clipWeight)
                {
                    continue;
                }

                clipWeight = clipInfo.weight;
                clipName = clipInfo.clip.name ?? string.Empty;
            }

            string poseKey = string.IsNullOrEmpty(clipName)
                ? info.fullPathHash.ToString()
                : clipName + "|" + info.fullPathHash;

            float normalized = info.normalizedTime;
            if (profile != null && profile.rewindUnloop)
            {
                normalized = GetUnroller(character.CharacterId, poseKey).ToMonotonic(normalized);
            }

            state = new ControllerState
            {
                PoseKey = poseKey,
                NormalizedTime = normalized,
                Length = info.length,
                Speed = info.speed,
                ClipName = clipName,
                LayerIndex = layer
            };
            return true;
        }

        private static int ResolveLayer(Animator animator, GameProfile profile)
        {
            if (profile == null)
            {
                return 0;
            }

            if (!string.IsNullOrEmpty(profile.poseLayerName))
            {
                int bestLayer = -1;
                float bestWeight = float.MinValue;
                for (int i = 0; i < animator.layerCount; i++)
                {
                    if (!string.Equals(animator.GetLayerName(i), profile.poseLayerName, StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    float weight = animator.GetLayerWeight(i);
                    if (weight > bestWeight)
                    {
                        bestWeight = weight;
                        bestLayer = i;
                    }
                }

                if (bestLayer >= 0)
                {
                    return bestLayer;
                }
            }

            return profile.poseLayer;
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
