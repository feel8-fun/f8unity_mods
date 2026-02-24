using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using F8SkeletonStreamer.NonPortable;
using HarmonyLib;
using F8SkeletonStreamer.Profiles;
using UnityEngine;

namespace F8SkeletonStreamer.Triggering
{
    internal sealed class HookTriggerSource : MonoBehaviour, ITriggerSource
    {
        private const string HarmonyId = "com.feel8.f8-skeleton-streamer.hooks";

        private static HookTriggerSource _instance;
        private static MethodInfo _startPostfix;
        private static MethodInfo _endPrefix;
        private static MethodInfo _observePostfix;

        private readonly HashSet<MethodBase> _startMethods = new HashSet<MethodBase>();
        private readonly HashSet<MethodBase> _endMethods = new HashSet<MethodBase>();
        private readonly HashSet<MethodBase> _observeMethods = new HashSet<MethodBase>();

        private Harmony _harmony;
        private ProfileResolver _resolver;

        public event Action<TriggerSignal> OnSignal;

        private void Awake()
        {
            _instance = this;
            _startPostfix = AccessTools.Method(typeof(HookTriggerSource), "StartHookPostfix");
            _endPrefix = AccessTools.Method(typeof(HookTriggerSource), "EndHookPrefix");
            _observePostfix = AccessTools.Method(typeof(HookTriggerSource), "ObserveHookPostfix");
        }

        private void Start()
        {
            _resolver = GetComponent<ProfileResolver>();
            if (_resolver != null && _resolver.ActiveProfile == null)
            {
                _resolver.Reload();
            }
            _harmony = new Harmony(HarmonyId);
            InstallHooks();
        }

        public void ReloadHooks()
        {
            if (_harmony == null)
            {
                return;
            }

            try
            {
                _harmony.UnpatchSelf();
            }
            catch
            {
            }

            _startMethods.Clear();
            _endMethods.Clear();
            _observeMethods.Clear();
            InstallHooks();
        }

        private void OnDestroy()
        {
            try
            {
                if (_harmony != null)
                {
                    _harmony.UnpatchSelf();
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning("HookTriggerSource unpatch failed: " + e);
            }
            _startMethods.Clear();
            _endMethods.Clear();
            _observeMethods.Clear();
            if (ReferenceEquals(_instance, this))
            {
                _instance = null;
            }
        }

        private void InstallHooks()
        {
            GameProfile profile = _resolver != null ? _resolver.ActiveProfile : null;
            string[] startMethods = profile != null && profile.hooksStart != null
                ? profile.hooksStart.Where(item => !string.IsNullOrEmpty(item)).Distinct().ToArray()
                : new string[0];
            string[] endMethods = profile != null && profile.hooksEnd != null
                ? profile.hooksEnd.Where(item => !string.IsNullOrEmpty(item)).Distinct().ToArray()
                : new string[0];
            string[] observeMethods = profile != null && profile.hooksObserve != null
                ? profile.hooksObserve.Where(item => !string.IsNullOrEmpty(item)).Distinct().ToArray()
                : new string[0];

            int patchedStart = 0;
            int patchedEnd = 0;
            int patchedObserve = 0;

            foreach (string descriptor in startMethods)
            {
                if (PatchAsStart(descriptor))
                {
                    patchedStart++;
                }
            }
            foreach (string descriptor in endMethods)
            {
                if (PatchAsEnd(descriptor))
                {
                    patchedEnd++;
                }
            }
            foreach (string descriptor in observeMethods)
            {
                if (PatchAsObserve(descriptor))
                {
                    patchedObserve++;
                }
            }

            Globals.Logger?.LogInfo(
                "[hook] patch summary: start=" + patchedStart +
                ", end=" + patchedEnd +
                ", observe=" + patchedObserve);
        }

        private bool PatchAsStart(string descriptor)
        {
            MethodInfo method = AccessTools.Method(descriptor);
            if (method == null)
            {
                Globals.Logger?.LogWarning("[hook] start descriptor not found: " + descriptor);
                return false;
            }
            if (_startMethods.Add(method))
            {
                _harmony.Patch(method, postfix: new HarmonyMethod(_startPostfix));
                return true;
            }

            return false;
        }

        private bool PatchAsEnd(string descriptor)
        {
            MethodInfo method = AccessTools.Method(descriptor);
            if (method == null)
            {
                Globals.Logger?.LogWarning("[hook] end descriptor not found: " + descriptor);
                return false;
            }
            if (_endMethods.Add(method))
            {
                _harmony.Patch(method, prefix: new HarmonyMethod(_endPrefix));
                return true;
            }

            return false;
        }

        private bool PatchAsObserve(string descriptor)
        {
            MethodInfo method = AccessTools.Method(descriptor);
            if (method == null)
            {
                Globals.Logger?.LogWarning("[hook] observe descriptor not found: " + descriptor);
                return false;
            }
            if (_observeMethods.Add(method))
            {
                _harmony.Patch(method, postfix: new HarmonyMethod(_observePostfix));
                return true;
            }

            return false;
        }

        private void Emit(TriggerSignal signal)
        {
            Action<TriggerSignal> handler = OnSignal;
            if (handler != null)
            {
                handler(signal);
            }
        }

        private void HandleStart(MethodBase method, object instance)
        {
            Globals.Logger?.LogInfo("[hook] HStart " + GetMethodName(method) + " instance=" + BuildInstanceLabel(instance));
            Emit(new TriggerSignal
            {
                Type = TriggerEventType.HStart,
                Source = "hook",
                Method = GetMethodName(method),
                HookInstance = instance
            });
            HandleHookCalled(method, instance);
        }

        private void HandleEnd(MethodBase method, object instance)
        {
            Globals.Logger?.LogInfo("[hook] HEnd " + GetMethodName(method) + " instance=" + BuildInstanceLabel(instance));
            Emit(new TriggerSignal
            {
                Type = TriggerEventType.HEnd,
                Source = "hook",
                Method = GetMethodName(method),
                HookInstance = instance
            });
            HandleHookCalled(method, instance);
        }

        private void HandleHookCalled(MethodBase method, object instance)
        {
            Emit(new TriggerSignal
            {
                Type = TriggerEventType.HookCalled,
                Source = "hook",
                Method = GetMethodName(method),
                HookInstance = instance
            });
        }

        private static string BuildInstanceLabel(object instance)
        {
            if (instance == null)
            {
                return "null";
            }

            string typeName = instance.GetType().FullName ?? instance.GetType().Name;
            try
            {
                UnityEngine.Object unityObject = instance as UnityEngine.Object;
                if (unityObject != null)
                {
                    string objectName = string.IsNullOrEmpty(unityObject.name) ? "<unnamed>" : unityObject.name;
                    return typeName + "('" + objectName + "')";
                }
            }
            catch
            {
            }

            return typeName;
        }

        private static string GetMethodName(MethodBase method)
        {
            if (method == null)
            {
                return "unknown";
            }
            return method.DeclaringType.FullName + ":" + method.Name;
        }

        private static void StartHookPostfix(MethodBase __originalMethod, object __instance)
        {
            if (_instance != null)
            {
                _instance.HandleStart(__originalMethod, __instance);
            }
        }

        private static void EndHookPrefix(MethodBase __originalMethod, object __instance)
        {
            if (_instance != null)
            {
                _instance.HandleEnd(__originalMethod, __instance);
            }
        }

        private static void ObserveHookPostfix(MethodBase __originalMethod, object __instance)
        {
            if (_instance != null)
            {
                _instance.HandleHookCalled(__originalMethod, __instance);
            }
        }

    }
}
