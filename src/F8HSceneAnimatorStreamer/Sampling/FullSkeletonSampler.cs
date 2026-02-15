using System.Collections.Generic;
using F8HSceneAnimatorStreamer.Discovery;
using UnityEngine;
using CharacterModel = F8HSceneAnimatorStreamer.Discovery.CharacterInfo;

namespace F8HSceneAnimatorStreamer.Sampling
{
    internal sealed class FullSkeletonSampler : MonoBehaviour, ISkeletonSampler
    {
        private sealed class CachedRig
        {
            public Transform Root;
            public Transform[] Bones;
            public string[] Paths;
        }

        private readonly Dictionary<int, CachedRig> _cache = new Dictionary<int, CachedRig>();

        public BoneSample[] Sample(CharacterModel character)
        {
            if (character == null || character.Root == null)
            {
                return new BoneSample[0];
            }

            int id = character.CharacterId;
            CachedRig cachedRig;
            if (!_cache.TryGetValue(id, out cachedRig) || cachedRig.Root == null)
            {
                cachedRig = BuildCache(character.Root.transform);
                _cache[id] = cachedRig;
            }

            var result = new BoneSample[cachedRig.Bones.Length];
            for (int i = 0; i < cachedRig.Bones.Length; i++)
            {
                Transform tf = cachedRig.Bones[i];
                Quaternion q = tf.rotation;
                Vector3 p = tf.position;
                result[i] = new BoneSample
                {
                    BonePath = cachedRig.Paths[i],
                    X = p.x,
                    Y = p.y,
                    Z = p.z,
                    Qw = q.w,
                    Qx = q.x,
                    Qy = q.y,
                    Qz = q.z
                };
            }
            return result;
        }

        private static CachedRig BuildCache(Transform root)
        {
            Transform[] bones = root.GetComponentsInChildren<Transform>(true);
            string[] paths = new string[bones.Length];
            for (int i = 0; i < bones.Length; i++)
            {
                paths[i] = BuildRelativePath(root, bones[i]);
            }

            return new CachedRig
            {
                Root = root,
                Bones = bones,
                Paths = paths
            };
        }

        private static string BuildRelativePath(Transform root, Transform bone)
        {
            if (root == bone)
            {
                return root.name;
            }

            var segments = new List<string>();
            Transform current = bone;
            while (current != null && current != root)
            {
                segments.Add(current.name);
                current = current.parent;
            }
            segments.Add(root.name);
            segments.Reverse();
            return string.Join("/", segments.ToArray());
        }
    }
}
