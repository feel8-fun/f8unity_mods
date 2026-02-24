using System;
using System.Collections.Generic;
using F8Live2DStreamer.Profiles;
using UnityEngine;

namespace F8Live2DStreamer.Discovery
{
    internal sealed class ProfileCharacterProvider : MonoBehaviour, ICharacterProvider
    {
        private const float DiscoveryRetryIntervalSeconds = 0.25f;

        private readonly ExpressionEvaluator _evaluator = new ExpressionEvaluator();

        private ProfileResolver _resolver;
        private bool _sessionActive;
        private object _hookInstance;
        private string _lastHookMethod = string.Empty;
        private CharacterInfo[] _cachedCharacters = new CharacterInfo[0];
        private bool _hasCharacterLock;
        private float _nextDiscoveryAt;
        private string _cachedProfileId = string.Empty;
        private object _cachedHookInstance;

        public bool HasActiveSession
        {
            get { return _sessionActive; }
        }

        public object ActiveHookInstance
        {
            get { return _hookInstance; }
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
            ClearCharacterCache();
        }

        public void EndSession(string hookMethod)
        {
            _sessionActive = false;
            _hookInstance = null;
            _lastHookMethod = hookMethod ?? string.Empty;
            ClearCharacterCache();
        }

        public CharacterInfo[] GetActiveCharacters()
        {
            if (!_sessionActive || _resolver == null || _resolver.ActiveProfile == null)
            {
                ClearCharacterCache();
                return new CharacterInfo[0];
            }

            GameProfile profile = _resolver.ActiveProfile;
            if (_hasCharacterLock && IsCharacterCacheValid(profile))
            {
                return _cachedCharacters;
            }

            if (Time.unscaledTime < _nextDiscoveryAt)
            {
                return _cachedCharacters;
            }

            var characters = new List<CharacterInfo>();
            Transform[] femaleRoots = _evaluator.EvaluateTransforms(_hookInstance, profile.femaleRootsExpr);
            object[] femaleControllers = _evaluator.EvaluateObjects(_hookInstance, profile.femaleControllerExpr);
            BuildCharactersForRole(
                profile,
                CharacterRole.Female,
                femaleRoots,
                femaleControllers,
                profile.maxFemaleCount,
                characters);

            Transform[] maleRoots = _evaluator.EvaluateTransforms(_hookInstance, profile.maleRootsExpr);
            object[] maleControllers = _evaluator.EvaluateObjects(_hookInstance, profile.maleControllerExpr);
            BuildCharactersForRole(
                profile,
                CharacterRole.Male,
                maleRoots,
                maleControllers,
                profile.maxMaleCount,
                characters);

            _cachedCharacters = characters.ToArray();
            _cachedProfileId = profile.id ?? string.Empty;
            _cachedHookInstance = _hookInstance;
            _hasCharacterLock = _cachedCharacters.Length > 0;
            _nextDiscoveryAt = Time.unscaledTime + DiscoveryRetryIntervalSeconds;
            return _cachedCharacters;
        }

        private void BuildCharactersForRole(
            GameProfile profile,
            CharacterRole role,
            Transform[] roots,
            object[] controllers,
            int maxByConfig,
            IList<CharacterInfo> destination)
        {
            int candidateCount = Math.Max(roots.Length, controllers.Length);
            if (candidateCount == 0)
            {
                return;
            }

            int maxCount = maxByConfig > 0 ? maxByConfig : candidateCount;
            int emitted = 0;

            for (int index = 0; index < candidateCount && emitted < maxCount; index++)
            {
                Transform root = index < roots.Length ? roots[index] : null;
                object controllerObject = index < controllers.Length ? controllers[index] : null;

                Animator animator = null;
                Animation animation = null;

                if (profile.GetControllerType() == ControllerType.Animator)
                {
                    animator = ResolveAnimator(controllerObject);
                    if (animator == null && root != null)
                    {
                        animator = root.GetComponentInChildren<Animator>(true);
                    }
                    controllerObject = animator;
                }
                else
                {
                    animation = ResolveAnimation(controllerObject);
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

                if (profile.activeOnly && root != null && !root.gameObject.activeInHierarchy)
                {
                    continue;
                }

                var map = new Dictionary<string, Transform>(StringComparer.OrdinalIgnoreCase);
                AddKeypoints(profile, role, map, root);
                if (map.Count == 0)
                {
                    continue;
                }

                UnityEngine.Object unityController = controllerObject as UnityEngine.Object;
                int baseId = root != null
                    ? root.GetInstanceID()
                    : (unityController != null ? unityController.GetInstanceID() : (index + 1));
                int characterId = role == CharacterRole.Male ? (baseId ^ 0x5A5A0000) : baseId;

                string baseName = root != null
                    ? root.name
                    : (unityController != null ? unityController.name : ("character_" + index));
                string characterName = (role == CharacterRole.Female ? "female:" : "male:") + (baseName ?? ("character_" + index));

                destination.Add(new CharacterInfo
                {
                    CharacterId = characterId,
                    CharacterName = characterName,
                    Root = root != null ? root.gameObject : null,
                    Animator = animator,
                    Animation = animation,
                    Controller = controllerObject,
                    Role = role,
                    RoleIndex = index,
                    ProfileId = profile.id,
                    KeypointMap = map
                });
                emitted++;
            }
        }

        private void AddKeypoints(GameProfile profile,
            CharacterRole role,
            IDictionary<string, Transform> target,
            Transform root)
        {
            if (root != null)
            {
                target[role == CharacterRole.Male
                    ? KeypointKind.MaleRoot.ToString()
                    : KeypointKind.FemaleRoot.ToString()] = root;
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
                if (!ShouldApplyKeypoint(role, kind))
                {
                    continue;
                }

                string key = kind.ToString();
                if (target.ContainsKey(key))
                {
                    continue;
                }

                if (kind == KeypointKind.FemaleRoot || kind == KeypointKind.MaleRoot)
                {
                    bool isRoleRoot = (role == CharacterRole.Female && kind == KeypointKind.FemaleRoot)
                        || (role == CharacterRole.Male && kind == KeypointKind.MaleRoot);
                    if (isRoleRoot && root != null)
                    {
                        target[key] = root;
                    }
                    continue;
                }

                if (root == null || string.IsNullOrEmpty(binding.pathOrName))
                {
                    continue;
                }

                Transform found = _evaluator.FindByPathOrName(root, binding.pathOrName, useRegex, profile.activeOnly);
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

        private static Animator ResolveAnimator(object controllerObject)
        {
            if (controllerObject == null)
            {
                return null;
            }

            Animator animator = controllerObject as Animator;
            if (animator != null)
            {
                return animator;
            }

            Component component = controllerObject as Component;
            if (component != null)
            {
                animator = component.GetComponentInChildren<Animator>(true);
                if (animator != null)
                {
                    return animator;
                }
            }

            GameObject gameObject = controllerObject as GameObject;
            if (gameObject != null)
            {
                animator = gameObject.GetComponentInChildren<Animator>(true);
                if (animator != null)
                {
                    return animator;
                }
            }

            return null;
        }

        private static Animation ResolveAnimation(object controllerObject)
        {
            if (controllerObject == null)
            {
                return null;
            }

            Animation animation = controllerObject as Animation;
            if (animation != null)
            {
                return animation;
            }

            Component component = controllerObject as Component;
            if (component != null)
            {
                animation = component.GetComponentInChildren<Animation>(true);
                if (animation != null)
                {
                    return animation;
                }
            }

            GameObject gameObject = controllerObject as GameObject;
            if (gameObject != null)
            {
                animation = gameObject.GetComponentInChildren<Animation>(true);
                if (animation != null)
                {
                    return animation;
                }
            }

            return null;
        }

        private static bool ShouldApplyKeypoint(CharacterRole role, KeypointKind kind)
        {
            if (role == CharacterRole.Female)
            {
                return kind != KeypointKind.MaleRoot && kind != KeypointKind.MalePenisBase;
            }

            return kind != KeypointKind.FemaleRoot
                && kind != KeypointKind.Vagina
                && kind != KeypointKind.Anus
                && kind != KeypointKind.LeftBreast
                && kind != KeypointKind.RightBreast;
        }

        private bool IsCharacterCacheValid(GameProfile profile)
        {
            if (!_hasCharacterLock || _cachedCharacters == null || _cachedCharacters.Length == 0)
            {
                return false;
            }

            if (!ReferenceEquals(_cachedHookInstance, _hookInstance))
            {
                return false;
            }

            if (!string.Equals(_cachedProfileId, profile.id ?? string.Empty, StringComparison.Ordinal))
            {
                return false;
            }

            for (int i = 0; i < _cachedCharacters.Length; i++)
            {
                CharacterInfo character = _cachedCharacters[i];
                if (character == null || character.Root == null)
                {
                    return false;
                }

                if (profile.activeOnly && !character.Root.activeInHierarchy)
                {
                    return false;
                }

                if (character.KeypointMap == null || character.KeypointMap.Count == 0)
                {
                    return false;
                }

                foreach (KeyValuePair<string, Transform> kvp in character.KeypointMap)
                {
                    Transform tf = kvp.Value;
                    if (tf == null)
                    {
                        return false;
                    }

                    if (profile.activeOnly && !tf.gameObject.activeInHierarchy)
                    {
                        return false;
                    }
                }
            }

            return true;
        }

        private void ClearCharacterCache()
        {
            _cachedCharacters = new CharacterInfo[0];
            _hasCharacterLock = false;
            _cachedProfileId = string.Empty;
            _cachedHookInstance = null;
            _nextDiscoveryAt = 0f;
        }
    }
}
