using System;
using System.IO;
using F8Live2DStreamer.Common;
using F8Live2DStreamer.Config;
using F8Live2DStreamer.Discovery;
using F8Live2DStreamer.NonPortable;
using F8Live2DStreamer.Protocol;
using F8Live2DStreamer.Profiles;
using F8Live2DStreamer.Sampling;
using F8Live2DStreamer.Transport;
using F8Live2DStreamer.Triggering;
using UnityEngine;

namespace F8Live2DStreamer.Bootstrap
{
    internal sealed class ExporterRuntime : MonoBehaviour
    {
        private const string Live2DSchema = "unity.live2d.drawables.bbox.v1";
        private const string DefaultKeypointSchema = "unity.keypoints.realtime.v1";

        private HookTriggerSource _hookSource;
        private ProfileResolver _profileResolver;
        private ILive2DCharacterProvider _characterProvider;
        private ILive2DDrawableSampler _sampler;

        private UdpDatagramSender _sender;
        private Live2DDrawablePacketEncoder _drawableEncoder;
        private SkeletonPacketEncoder _skeletonEncoder;
        private DrawableKeypointSampler _drawableKeypointSampler;

        private bool _hookActive;
        private float _nextFrameAt;
        private ulong _frameId;
        private CaptureMode _lastMode = (CaptureMode)(-1);

        private float _nextHotReloadAt;
        private string _profilePath = string.Empty;
        private long _lastConfigWriteTicks = -1;
        private long _lastProfileWriteTicks = -1;
        private string _activeHost = string.Empty;
        private int _activePort = -1;

        private void Start()
        {
            _hookSource = GetComponent<HookTriggerSource>();
            _profileResolver = GetComponent<ProfileResolver>();
            _characterProvider = GetComponent<Live2DCharacterProvider>();
            _sampler = GetComponent<Live2DDrawableSampler>();
            _drawableEncoder = new Live2DDrawablePacketEncoder();
            _skeletonEncoder = new SkeletonPacketEncoder();
            _drawableKeypointSampler = new DrawableKeypointSampler();

            string baseDirectory = Path.GetDirectoryName(typeof(ProfileResolver).Assembly.Location) ?? string.Empty;
            _profilePath = Path.Combine(baseDirectory, "profile.json");
            _lastConfigWriteTicks = ReadWriteTicks(ExporterConfig.ConfigPath);
            _lastProfileWriteTicks = ReadWriteTicks(_profilePath);

            EnsureSender();

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

            if (_sender != null)
            {
                _sender.Dispose();
                _sender = null;
            }
        }

        private void Update()
        {
            PollConfigAndProfileHotReload();
        }

        private void LateUpdate()
        {
            if (_characterProvider == null || _sampler == null || _sender == null)
            {
                return;
            }

            GameProfile profile = _profileResolver != null ? _profileResolver.ActiveProfile : null;
            if (profile == null)
            {
                return;
            }

            CaptureMode mode = ResolveCaptureMode(profile);
            if (_lastMode != mode)
            {
                _lastMode = mode;
                Globals.Logger?.LogInfo("[live2d] capture mode=" + mode);
            }

            bool shouldCapture = mode == CaptureMode.AlwaysOn || (mode == CaptureMode.HookOnly && _hookActive);
            if (!shouldCapture)
            {
                return;
            }

            float interval = 1f / Mathf.Max(1, ExporterConfig.TargetFps.Value);
            if (Time.unscaledTime < _nextFrameAt)
            {
                return;
            }
            _nextFrameAt = Mathf.Max(_nextFrameAt + interval, Time.unscaledTime + 0.0001f);

            Live2DCharacterInfo[] characters = _characterProvider.GetActiveCharacters();
            if (characters == null || characters.Length == 0)
            {
                return;
            }

            _frameId++;
            long timestampMs = TimeUtil.NowMs();

            for (int i = 0; i < characters.Length; i++)
            {
                Live2DCharacterInfo character = characters[i];
                bool emitDrawables = profile.emitDrawablesBbox;
                bool emitKeypoints = profile.emitKeypointsFromDrawables;
                if (!emitDrawables && !emitKeypoints)
                {
                    continue;
                }

                DrawableSample[] samples = _sampler.Sample(character, profile);
                if (samples == null || samples.Length == 0)
                {
                    continue;
                }

                if (emitDrawables)
                {
                    Live2DCharacterFrame frame = new Live2DCharacterFrame
                    {
                        FrameId = _frameId,
                        TimestampMs = timestampMs,
                        CharacterId = character.CharacterId,
                        CharacterName = character.CharacterName,
                        Drawables = samples
                    };

                    byte[][] packets = _drawableEncoder.EncodeChunks(frame, Live2DSchema, ExporterConfig.MaxUdpPayloadBytes.Value);
                    for (int p = 0; p < packets.Length; p++)
                    {
                        _sender.Send(packets[p]);
                    }
                }

                if (!emitKeypoints)
                {
                    continue;
                }

                BoneSample[] bones = _drawableKeypointSampler.Sample(samples, profile);
                if (bones == null || bones.Length == 0)
                {
                    continue;
                }

                SendKeypointPackets(character, bones, profile, timestampMs);
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
                if (_characterProvider != null)
                {
                    _characterProvider.StartSession(signal.HookInstance, signal.Method);
                }
                return;
            }

            if (signal.Type == TriggerEventType.HEnd)
            {
                _hookActive = false;
                if (_characterProvider != null)
                {
                    _characterProvider.EndSession(signal.Method);
                }
            }
        }

        private CaptureMode ResolveCaptureMode(GameProfile profile)
        {
            string selected = profile.captureMode;
            if (string.IsNullOrEmpty(selected))
            {
                selected = ExporterConfig.CaptureMode.Value;
            }

            CaptureMode requested = ParseMode(selected);
            if (requested != CaptureMode.Auto)
            {
                return requested;
            }

            bool hasHooks = (profile.hooksStart != null && profile.hooksStart.Length > 0)
                || (profile.hooksEnd != null && profile.hooksEnd.Length > 0);
            return hasHooks ? CaptureMode.HookOnly : CaptureMode.AlwaysOn;
        }

        private static CaptureMode ParseMode(string mode)
        {
            if (string.Equals(mode, "HookOnly", StringComparison.OrdinalIgnoreCase))
            {
                return CaptureMode.HookOnly;
            }
            if (string.Equals(mode, "AlwaysOn", StringComparison.OrdinalIgnoreCase))
            {
                return CaptureMode.AlwaysOn;
            }
            return CaptureMode.Auto;
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

            EnsureSender();
        }

        private void EnsureSender()
        {
            string host = ExporterConfig.Live2DHost.Value ?? "127.0.0.1";
            int port = ExporterConfig.Live2DPort.Value;
            if (_sender != null
                && string.Equals(_activeHost, host, StringComparison.OrdinalIgnoreCase)
                && _activePort == port)
            {
                return;
            }

            if (_sender != null)
            {
                _sender.Dispose();
                _sender = null;
            }

            _sender = new UdpDatagramSender(host, port);
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

        private void SendKeypointPackets(Live2DCharacterInfo character, BoneSample[] bones, GameProfile profile, long timestampMs)
        {
            if (_sender == null || _skeletonEncoder == null || character == null || bones == null || bones.Length == 0)
            {
                return;
            }

            string schema = profile != null ? profile.keypointSchema : null;
            if (string.IsNullOrEmpty(schema))
            {
                schema = DefaultKeypointSchema;
            }

            CharacterFrame frame = new CharacterFrame
            {
                FrameId = _frameId,
                TimestampMs = timestampMs,
                CharacterId = character.CharacterId,
                CharacterName = character.CharacterName,
                Bones = bones,
                HasAnimationContext = false,
                NormalizedTime = 0f,
                LayerIndex = 0,
                ClipName = string.Empty,
                PoseKey = "live2d_drawable_bbox_center"
            };

            byte[][] packets = _skeletonEncoder.EncodeChunks(frame, schema, ExporterConfig.MaxUdpPayloadBytes.Value);
            for (int i = 0; i < packets.Length; i++)
            {
                _sender.Send(packets[i]);
            }
        }
    }
}
