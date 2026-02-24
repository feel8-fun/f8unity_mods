using System;
using System.Collections.Generic;
using F8Live2DStreamer.Config;
using F8Live2DStreamer.NonPortable;
using F8Live2DStreamer.Profiles;
using UnityEngine;

namespace F8Live2DStreamer.Discovery
{
    internal sealed class Live2DCharacterProvider : MonoBehaviour, ILive2DCharacterProvider
    {
        private readonly ExpressionEvaluator _evaluator = new ExpressionEvaluator();

        private ProfileResolver _resolver;
        private bool _sessionActive;
        private object _hookInstance;
        private string _lastHookMethod = string.Empty;

        private Live2DCharacterInfo[] _cachedCharacters = new Live2DCharacterInfo[0];
        private float _nextDiscoveryAt;
        private int _lastDiscoveryCount = -1;

        public bool HasActiveSession
        {
            get { return _sessionActive; }
        }

        public object ActiveHookInstance
        {
            get { return _hookInstance; }
        }

        private void Awake()
        {
            _resolver = GetComponent<ProfileResolver>();
        }

        public void StartSession(object hookInstance, string hookMethod)
        {
            _sessionActive = true;
            _hookInstance = hookInstance;
            _lastHookMethod = hookMethod ?? string.Empty;
            ClearCache();
        }

        public void EndSession(string hookMethod)
        {
            _sessionActive = false;
            _hookInstance = null;
            _lastHookMethod = hookMethod ?? string.Empty;
            ClearCache();
        }

        public Live2DCharacterInfo[] GetActiveCharacters()
        {
            GameProfile profile = _resolver != null ? _resolver.ActiveProfile : null;
            if (profile == null)
            {
                ClearCache();
                return new Live2DCharacterInfo[0];
            }

            if (Time.unscaledTime < _nextDiscoveryAt)
            {
                return _cachedCharacters;
            }

            var discovered = new List<Transform>();
            var seen = new HashSet<int>();

            if (profile.autoDiscoverCubism)
            {
                AddAutoDiscoveredRoots(profile, discovered, seen);
            }

            Transform[] exprRoots = _evaluator.EvaluateTransforms(_hookInstance, profile.live2dRootsExpr);
            AddRoots(profile, exprRoots, discovered, seen);

            if (profile.maxModelCount > 0 && discovered.Count > profile.maxModelCount)
            {
                discovered.RemoveRange(profile.maxModelCount, discovered.Count - profile.maxModelCount);
            }

            var result = new Live2DCharacterInfo[discovered.Count];
            for (int i = 0; i < discovered.Count; i++)
            {
                Transform root = discovered[i];
                result[i] = new Live2DCharacterInfo
                {
                    CharacterId = root.GetInstanceID(),
                    CharacterName = root.name ?? ("live2d_" + i),
                    Root = root.gameObject
                };
            }

            _cachedCharacters = result;
            float interval = Mathf.Max(0.05f, ExporterConfig.DiscoveryIntervalMs.Value / 1000f);
            _nextDiscoveryAt = Time.unscaledTime + interval;

            if (ExporterConfig.DebugLogDiscovery.Value && _lastDiscoveryCount != result.Length)
            {
                _lastDiscoveryCount = result.Length;
                string source = string.IsNullOrEmpty(_lastHookMethod) ? "none" : _lastHookMethod;
                Globals.Logger?.LogInfo("[live2d] discovery roots=" + result.Length + " hook=" + source);
            }

            return _cachedCharacters;
        }

        private void AddAutoDiscoveredRoots(GameProfile profile, IList<Transform> destination, HashSet<int> seen)
        {
            Component[] objects = UnityEngine.Object.FindObjectsOfType<Component>();
            for (int i = 0; i < objects.Length; i++)
            {
                Component component = objects[i];
                if (component == null || component.transform == null)
                {
                    continue;
                }

                Transform root = ResolveAutoRoot(component);
                if (root == null)
                {
                    continue;
                }

                AddRoot(profile, root, destination, seen);
            }
        }

        private static Transform ResolveAutoRoot(Component component)
        {
            string typeName = component.GetType().Name;
            if (typeName.IndexOf("CubismModel", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                return component.transform;
            }

            if (typeName.IndexOf("CubismDrawable", StringComparison.OrdinalIgnoreCase) < 0)
            {
                return null;
            }

            Transform current = component.transform;
            while (current != null)
            {
                Component[] siblings = current.GetComponents<Component>();
                for (int i = 0; i < siblings.Length; i++)
                {
                    Component sibling = siblings[i];
                    if (sibling == null)
                    {
                        continue;
                    }

                    string siblingType = sibling.GetType().Name;
                    if (siblingType.IndexOf("CubismModel", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return current;
                    }
                }

                current = current.parent;
            }

            return component.transform.root;
        }

        private static void AddRoots(GameProfile profile, Transform[] roots, IList<Transform> destination, HashSet<int> seen)
        {
            for (int i = 0; i < roots.Length; i++)
            {
                AddRoot(profile, roots[i], destination, seen);
            }
        }

        private static void AddRoot(GameProfile profile, Transform root, IList<Transform> destination, HashSet<int> seen)
        {
            if (root == null)
            {
                return;
            }

            if (profile.activeOnly && !root.gameObject.activeInHierarchy)
            {
                return;
            }

            int id = root.GetInstanceID();
            if (seen.Contains(id))
            {
                return;
            }

            seen.Add(id);
            destination.Add(root);
        }

        private void ClearCache()
        {
            _cachedCharacters = new Live2DCharacterInfo[0];
            _nextDiscoveryAt = 0f;
            _lastDiscoveryCount = -1;
        }
    }
}
