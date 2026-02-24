using System;
using System.Collections.Generic;
using F8SkeletonStreamer.Discovery;

namespace F8SkeletonStreamer.Sampling
{
    internal sealed class KeypointSampler : UnityEngine.MonoBehaviour, IKeypointSampler
    {
        public BoneSample[] SampleRealtime(CharacterInfo character)
        {
            if (character == null || character.KeypointMap == null || character.KeypointMap.Count == 0)
            {
                return new BoneSample[0];
            }

            var samples = new List<BoneSample>(character.KeypointMap.Count);
            foreach (KeyValuePair<string, UnityEngine.Transform> kvp in character.KeypointMap)
            {
                UnityEngine.Transform tf = kvp.Value;
                if (tf == null)
                {
                    continue;
                }

                UnityEngine.Vector3 p = tf.position;
                UnityEngine.Quaternion q = tf.rotation;
                samples.Add(new BoneSample
                {
                    BonePath = kvp.Key,
                    X = p.x,
                    Y = p.y,
                    Z = p.z,
                    Qw = q.w,
                    Qx = q.x,
                    Qy = q.y,
                    Qz = q.z
                });
            }

            samples.Sort((a, b) => string.Compare(a.BonePath, b.BonePath, StringComparison.Ordinal));
            return samples.ToArray();
        }
    }
}
