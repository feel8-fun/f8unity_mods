using System;
using System.Collections.Generic;
using F8HSceneAnimatorStreamer.Profiles;
using UnityEngine;

namespace F8HSceneAnimatorStreamer.Discovery
{
    internal sealed class ProfileCharacterProvider : MonoBehaviour, ICharacterProvider
    {
        private readonly ExpressionEvaluator _evaluator = new ExpressionEvaluator();

        private ProfileResolver _resolver;
        private bool _sessionActive;
        private object _hookInstance;
        private string _lastHookMethod = string.Empty;

        public bool HasActiveSession
        {
            get { return _sessionActive; }
        }

        public string ActiveProfileId
        {
            get
            {
                if (_resolver == null || _resolver.ActiveProfile == null)
                {
                    return string.Empty;
                }
                return _resolver.ActiveProfile.id ?? string.Empty;
            }
        }

        private void Awake()
        {
            _resolver = GetComponent<ProfileResolver>();
        }

        public void StartSession(object hookInstance, string hookMethod)
        {
            _hookInstance = hookInstance;
            _lastHookMethod = hookMethod ?? string.Empty;
            _sessionActive = true;
        }

        public void EndSession(string hookMethod)
        {
            _sessionActive = false;
            _hookInstance = null;
            _lastHookMethod = hookMethod ?? string.Empty;
        }

        public CharacterInfo[] GetActiveCharacters()
        {
            if (!_sessionActive || _resolver == null || _resolver.ActiveProfile == null)
            {
                return new CharacterInfo[0];
            }

            GameProfile profile = _resolver.ActiveProfile;
            Transform[] roots = _evaluator.EvaluateTransforms(_hookInstance, profile.femaleRootsExpr);
            object[] controllers = _evaluator.EvaluateObjects(_hookInstance, profile.controllerExpr);
            Transform[] maleBases = _evaluator.EvaluateTransforms(_hookInstance, profile.malePenisBaseExpr);

            int maxCount = Math.Max(roots.Length, controllers.Length);
            if (profile.maxFemaleCount > 0)
            {
                maxCount = Math.Min(maxCount, profile.maxFemaleCount);
            }
            if (maxCount == 0)
            {
                maxCount = roots.Length > 0 ? roots.Length : controllers.Length;
            }

            var characters = new List<CharacterInfo>();
            for (int index = 0; index < maxCount; index++)
            {
                Transform root = index < roots.Length ? roots[index] : null;
                object controllerObject = index < controllers.Length ? controllers[index] : null;

                Animator animator = null;
                Animation animation = null;

                if (profile.GetControllerType() == ControllerType.Animator)
                {
                    animator = controllerObject as Animator;
                    if (animator == null && root != null)
                    {
                        animator = root.GetComponentInChildren<Animator>(true);
                    }
                    controllerObject = animator;
                }
                else
                {
                    animation = controllerObject as Animation;
                    if (animation == null && root != null)
                    {
                        animation = FindPlayingAnimation(root);
                    }
                    controllerObject = animation;
                }

                if (root == null)
                {
                    Component component = controllerObject as Component;
                    if (component != null)
                    {
                        root = component.transform;
                    }
                }

                if (root == null && controllerObject == null)
                {
                    continue;
                }

                var map = new Dictionary<string, Transform>(StringComparer.OrdinalIgnoreCase);
                AddKeypoints(profile, map, root, maleBases, index);

                if (map.Count == 0)
                {
                    continue;
                }

                UnityEngine.Object unityController = controllerObject as UnityEngine.Object;
                int characterId = root != null
                    ? root.GetInstanceID()
                    : (unityController != null ? unityController.GetInstanceID() : (index + 1));

                string name = root != null
                    ? root.name
                    : (unityController != null ? unityController.name : ("character_" + index));

                characters.Add(new CharacterInfo
                {
                    CharacterId = characterId,
                    CharacterName = name ?? ("character_" + index),
                    Root = root != null ? root.gameObject : null,
                    Animator = animator,
                    Animation = animation,
                    Controller = controllerObject,
                    FemaleIndex = index,
                    ProfileId = profile.id,
                    KeypointMap = map
                });
            }

            return characters.ToArray();
        }

        private void AddKeypoints(GameProfile profile,
            IDictionary<string, Transform> target,
            Transform root,
            Transform[] maleBases,
            int index)
        {
            if (root != null)
            {
                target[KeypointKind.FemaleRoot.ToString()] = root;
            }

            if (maleBases != null && maleBases.Length > 0)
            {
                Transform baseTransform = index < maleBases.Length ? maleBases[index] : maleBases[0];
                if (baseTransform != null)
                {
                    target[KeypointKind.MalePenisBase.ToString()] = baseTransform;
                }
            }

            if (profile.keypoints == null)
            {
                return;
            }

            bool useRegex = profile.useRegex;
            for (int i = 0; i < profile.keypoints.Length; i++)
            {
                KeypointBinding binding = profile.keypoints[i];
                if (binding == null)
                {
                    continue;
                }

                KeypointKind kind = binding.GetKind();
                string key = kind.ToString();
                if (target.ContainsKey(key))
                {
                    continue;
                }

                if (kind == KeypointKind.FemaleRoot)
                {
                    if (root != null)
                    {
                        target[key] = root;
                    }
                    continue;
                }

                if (kind == KeypointKind.MalePenisBase)
                {
                    continue;
                }

                if (root == null || string.IsNullOrEmpty(binding.pathOrName))
                {
                    continue;
                }

                Transform found = _evaluator.FindByPathOrName(root, binding.pathOrName, useRegex);
                if (found != null)
                {
                    target[key] = found;
                }
            }
        }

        private static Animation FindPlayingAnimation(Transform root)
        {
            Animation[] animations = root.GetComponentsInChildren<Animation>(true);
            for (int i = 0; i < animations.Length; i++)
            {
                Animation animation = animations[i];
                if (animation == null)
                {
                    continue;
                }

                foreach (AnimationState state in animation)
                {
                    if (animation.IsPlaying(state.name))
                    {
                        return animation;
                    }
                }
            }

            return animations.Length > 0 ? animations[0] : null;
        }
    }
}
