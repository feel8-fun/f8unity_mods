using BepInEx.Bootstrap;
using BepInEx.Logging;
using UnityEngine;

namespace F8HSceneAnimatorStreamer.NonPortable
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
                    _manager = new Manager(Chainloader.ManagerObject);
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

            public Manager(GameObject gameObject)
            {
                _gameObject = gameObject;
            }

            public T AddComponent<T>() where T : Component
            {
                T component = _gameObject.GetComponent<T>();
                if (component == null)
                {
                    component = _gameObject.AddComponent<T>();
                }
                return component;
            }

            public T GetComponent<T>() where T : Component
            {
                return _gameObject.GetComponent<T>();
            }
        }
    }
}
