using System;
using System.IO;
using F8SkeletonStreamer.Common;
using F8SkeletonStreamer.Config;
using F8SkeletonStreamer.Discovery;
using F8SkeletonStreamer.NonPortable;
using F8SkeletonStreamer.Protocol;
using F8SkeletonStreamer.Profiles;
using F8SkeletonStreamer.Sampling;
using F8SkeletonStreamer.Transport;
using F8SkeletonStreamer.Triggering;
using UnityEngine;
using CharacterModel = F8SkeletonStreamer.Discovery.CharacterInfo;

namespace F8SkeletonStreamer.Bootstrap
{
    internal sealed class ExporterRuntime : MonoBehaviour
    {
        private HookTriggerSource _hookSource;
        private ProfileResolver _profileResolver;
        private ICharacterProvider _characterProvider;
        private IKeypointSampler _keypointSampler;
        private ISkeletonSampler _fullSkeletonSampler;
        private IControllerStateReader _controllerReader;

        private UdpDatagramSender _skeletonSender;
        private SkeletonPacketEncoder _encoder;

        private bool _hookActive;
        private float _nextFrameAt;
        private ulong _frameId;

        private float _nextHotReloadAt;
        private string _profilePath = string.Empty;
        private long _lastConfigWriteTicks = -1;
        private long _lastProfileWriteTicks = -1;
        private string _activeHost = string.Empty;
        private int _activePort = -1;
        private float _noCharactersSince = -1f;

        private void Start()
        {
            _hookSource = GetComponent<HookTriggerSource>();
            _profileResolver = GetComponent<ProfileResolver>();
            _characterProvider = GetComponent<ProfileCharacterProvider>();
            _keypointSampler = GetComponent<KeypointSampler>();
            _fullSkeletonSampler = GetComponent<FullSkeletonSampler>();
            _controllerReader = GetComponent<ControllerStateRouter>();
            _encoder = new SkeletonPacketEncoder();

            string baseDirectory = Path.GetDirectoryName(typeof(ProfileResolver).Assembly.Location) ?? string.Empty;
            _profilePath = Path.Combine(baseDirectory, "profile.json");
            _lastConfigWriteTicks = ReadWriteTicks(ExporterConfig.ConfigPath);
            _lastProfileWriteTicks = ReadWriteTicks(_profilePath);

            EnsureSkeletonSender();

            if (_hookSource != null)
            {
                _hookSource.OnSignal += HandleTriggerSignal;
            }
        }

        private void OnDestroy()
        {
            if (_hookSource != null)
            {
                _hookSource.OnSignal -= HandleTriggerSignal;
            }

            if (_skeletonSender != null)
            {
                _skeletonSender.Dispose();
                _skeletonSender = null;
            }
        }

        private void Update()
        {
            PollConfigAndProfileHotReload();
        }

        private void LateUpdate()
        {
            if (!_hookActive || _characterProvider == null || _keypointSampler == null || _skeletonSender == null)
            {
                return;
            }

            float interval = 1f / Mathf.Max(1, ExporterConfig.TargetFps.Value);
            if (Time.unscaledTime < _nextFrameAt)
            {
                return;
            }
            _nextFrameAt = Mathf.Max(_nextFrameAt + interval, Time.unscaledTime + 0.0001f);

            CharacterModel[] characters = _characterProvider.GetActiveCharacters();
            if (characters.Length == 0)
            {
                TryAutoEndOnNoCharacters();
                return;
            }
            _noCharactersSince = -1f;

            _frameId++;
            long timestampMs = TimeUtil.NowMs();

            for (int i = 0; i < characters.Length; i++)
            {
                CharacterModel character = characters[i];
                BoneSample[] bones = _keypointSampler.SampleRealtime(character);
                if (bones == null || bones.Length == 0)
                {
                    continue;
                }

                ControllerState state = default(ControllerState);
                bool hasState = _controllerReader != null && _controllerReader.TryGetState(character, out state);
                if (!hasState)
                {
                    state.PoseKey = "no_controller";
                }

                SendSkeletonPackets(character, bones, "unity.keypoints.realtime.v1", timestampMs, hasState, state);

                if (IsDebugDumpEnabled() && _fullSkeletonSampler != null)
                {
                    BoneSample[] debugBones = _fullSkeletonSampler.Sample(character, ExporterConfig.DebugDumpIncludeInactive.Value);
                    if (debugBones != null && debugBones.Length > 0)
                    {
                        SendSkeletonPackets(character, debugBones, "unity.transforms.fullhierarchy.v1", timestampMs, hasState, state);
                    }
                }
            }
        }

        private void HandleTriggerSignal(TriggerSignal signal)
        {
            if (signal == null || signal.Source != "hook")
            {
                return;
            }

            if (signal.Type == TriggerEventType.HStart)
            {
                _hookActive = true;
                _noCharactersSince = -1f;
                if (_characterProvider != null)
                {
                    _characterProvider.StartSession(signal.HookInstance, signal.Method);
                }
                return;
            }

            if (signal.Type == TriggerEventType.HEnd)
            {
                _hookActive = false;
                _noCharactersSince = -1f;
                if (_characterProvider != null)
                {
                    _characterProvider.EndSession(signal.Method);
                }
            }
        }

        private void PollConfigAndProfileHotReload()
        {
            if (Time.unscaledTime < _nextHotReloadAt)
            {
                return;
            }
            _nextHotReloadAt = Time.unscaledTime + 0.5f;

            long configTicks = ReadWriteTicks(ExporterConfig.ConfigPath);
            long profileTicks = ReadWriteTicks(_profilePath);
            bool changed = configTicks != _lastConfigWriteTicks || profileTicks != _lastProfileWriteTicks;
            if (!changed)
            {
                return;
            }

            _lastConfigWriteTicks = configTicks;
            _lastProfileWriteTicks = profileTicks;

            ExporterConfig.Reload();
            if (_profileResolver != null)
            {
                _profileResolver.Reload();
            }
            if (_hookSource != null)
            {
                _hookSource.ReloadHooks();
            }
            EnsureSkeletonSender();
        }

        private bool IsDebugDumpEnabled()
        {
            GameProfile profile = _profileResolver != null ? _profileResolver.ActiveProfile : null;
            return profile != null && profile.debugDumpFullHierarchy;
        }

        private void TryAutoEndOnNoCharacters()
        {
            GameProfile profile = _profileResolver != null ? _profileResolver.ActiveProfile : null;
            float seconds = profile != null ? profile.autoEndOnNoCharactersSeconds : 0f;
            if (seconds <= 0f)
            {
                return;
            }

            if (_noCharactersSince < 0f)
            {
                _noCharactersSince = Time.unscaledTime;
                return;
            }

            if ((Time.unscaledTime - _noCharactersSince) < seconds)
            {
                return;
            }

            _hookActive = false;
            _noCharactersSince = -1f;
            if (_characterProvider != null)
            {
                _characterProvider.EndSession("auto_end_no_characters");
            }
            Globals.Logger?.LogInfo("[hook] auto-ended session: no active characters for " + seconds.ToString("0.###") + "s");
        }

        private void EnsureSkeletonSender()
        {
            string host = ExporterConfig.SkeletonHost.Value ?? "127.0.0.1";
            int port = ExporterConfig.SkeletonPort.Value;
            if (_skeletonSender != null
                && string.Equals(_activeHost, host, StringComparison.OrdinalIgnoreCase)
                && _activePort == port)
            {
                return;
            }

            if (_skeletonSender != null)
            {
                _skeletonSender.Dispose();
                _skeletonSender = null;
            }

            _skeletonSender = new UdpDatagramSender(host, port);
            _activeHost = host;
            _activePort = port;
        }

        private static long ReadWriteTicks(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return -1;
            }
            try
            {
                return File.Exists(path) ? File.GetLastWriteTimeUtc(path).Ticks : -1;
            }
            catch
            {
                return -1;
            }
        }

        private void SendSkeletonPackets(
            CharacterModel character,
            BoneSample[] bones,
            string schema,
            long timestampMs,
            bool hasAnimationContext,
            ControllerState controllerState)
        {
            CharacterFrame frame = new CharacterFrame
            {
                FrameId = _frameId,
                TimestampMs = timestampMs,
                CharacterId = character.CharacterId,
                CharacterName = character.CharacterName,
                Bones = bones,
                HasAnimationContext = hasAnimationContext,
                NormalizedTime = controllerState.NormalizedTime,
                LayerIndex = controllerState.LayerIndex,
                ClipName = controllerState.ClipName,
                PoseKey = controllerState.PoseKey
            };

            byte[][] packets = _encoder.EncodeChunks(frame, schema, ExporterConfig.MaxUdpPayloadBytes.Value);
            for (int i = 0; i < packets.Length; i++)
            {
                _skeletonSender.Send(packets[i]);
            }
        }
    }
}
