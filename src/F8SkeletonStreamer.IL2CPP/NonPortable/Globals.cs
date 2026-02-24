using BepInEx.Logging;
using Il2CppInterop.Runtime.Injection;
using UnityEngine;

namespace F8SkeletonStreamer.NonPortable
{
    internal static class Globals
    {
        private static Manager _manager;

        public static ManualLogSource Logger { get; private set; }

        public static Manager ManagerObject
        {
            get
            {
                if (_manager == null)
                {
                    _manager = new Manager();
                }
                return _manager;
            }
        }

        public static void Initialize(ManualLogSource logger)
        {
            Logger = logger;
        }

        internal sealed class Manager
        {
            private readonly GameObject _gameObject;

            public Manager()
            {
                _gameObject = new GameObject("F8SkeletonStreamer.Manager");
                _gameObject.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(_gameObject);
            }

            public T AddComponent<T>() where T : Component
            {
                ClassInjector.RegisterTypeInIl2Cpp<T>();
                T component = _gameObject.GetComponent<T>();
                if (component == null)
                {
                    component = _gameObject.AddComponent<T>();
                }
                return component;
            }

            public T GetComponent<T>() where T : Component
            {
                ClassInjector.RegisterTypeInIl2Cpp<T>();
                return _gameObject.GetComponent<T>();
            }
        }
    }
}
