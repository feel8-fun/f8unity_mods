using F8SkeletonStreamer.Discovery;
using UnityEngine;
using CharacterModel = F8SkeletonStreamer.Discovery.CharacterInfo;

namespace F8SkeletonStreamer.Sampling
{
    internal sealed class AnimatorContextReader : MonoBehaviour, IAnimationContextReader
    {
        public AnimatorLayerState[] ReadLayers(CharacterModel character)
        {
            if (character == null || character.Animator == null)
            {
                return new AnimatorLayerState[0];
            }

            Animator animator = character.Animator;
            int layerCount = animator.layerCount;
            var result = new AnimatorLayerState[layerCount];
            for (int layer = 0; layer < layerCount; layer++)
            {
                AnimatorStateInfo state = animator.GetCurrentAnimatorStateInfo(layer);
                AnimatorClipInfo[] clips = animator.GetCurrentAnimatorClipInfo(layer);
                string clipName = string.Empty;
                float clipWeight = 0f;
                for (int i = 0; i < clips.Length; i++)
                {
                    if (clips[i].weight > clipWeight && clips[i].clip != null)
                    {
                        clipName = clips[i].clip.name ?? string.Empty;
                        clipWeight = clips[i].weight;
                    }
                }

                result[layer] = new AnimatorLayerState
                {
                    LayerIndex = layer,
                    StateHash = state.fullPathHash,
                    StateName = state.fullPathHash.ToString(),
                    NormalizedTime = state.normalizedTime,
                    Length = state.length,
                    Speed = state.speed,
                    TopClipName = clipName,
                    TopClipWeight = clipWeight
                };
            }

            return result;
        }
    }
}
