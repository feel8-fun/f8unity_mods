using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using F8Live2DStreamer.NonPortable;
using F8Live2DStreamer.Profiles;

namespace F8Live2DStreamer.Sampling
{
    internal sealed class DrawableKeypointSampler
    {
        private readonly HashSet<string> _warnedKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        public BoneSample[] Sample(DrawableSample[] drawables, GameProfile profile)
        {
            if (drawables == null || drawables.Length == 0 || profile == null || profile.keypoints == null || profile.keypoints.Length == 0)
            {
                return new BoneSample[0];
            }

            var output = new List<BoneSample>(profile.keypoints.Length);
            var emitted = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            bool useRegex = profile.useRegex;

            for (int i = 0; i < profile.keypoints.Length; i++)
            {
                KeypointBinding binding = profile.keypoints[i];
                if (binding == null)
                {
                    continue;
                }

                string keyName = ResolveKeyName(binding);
                if (string.IsNullOrEmpty(keyName) || emitted.Contains(keyName))
                {
                    continue;
                }

                string matcher = binding.pathOrName ?? string.Empty;
                if (string.IsNullOrEmpty(matcher))
                {
                    continue;
                }

                DrawableSample? matched = FindDrawable(drawables, matcher, useRegex);
                if (!matched.HasValue)
                {
                    if (binding.required)
                    {
                        WarnOnce("missing_required_" + keyName + "_" + matcher,
                            "required drawable keypoint '" + keyName + "' not matched by '" + matcher + "'");
                    }
                    continue;
                }

                DrawableSample sample = matched.Value;
                output.Add(new BoneSample
                {
                    BonePath = keyName,
                    X = sample.CenterX,
                    Y = sample.CenterY,
                    Z = sample.CenterZ,
                    Qw = 1f,
                    Qx = 0f,
                    Qy = 0f,
                    Qz = 0f
                });
                emitted.Add(keyName);
            }

            output.Sort((a, b) => string.Compare(a.BonePath, b.BonePath, StringComparison.Ordinal));
            return output.ToArray();
        }

        private DrawableSample? FindDrawable(DrawableSample[] drawables, string matcher, bool useRegex)
        {
            for (int i = 0; i < drawables.Length; i++)
            {
                string path = drawables[i].DrawablePath ?? string.Empty;
                if (IsMatch(path, matcher, useRegex))
                {
                    return drawables[i];
                }
            }

            return null;
        }

        private bool IsMatch(string path, string matcher, bool useRegex)
        {
            if (!useRegex)
            {
                return string.Equals(path, matcher, StringComparison.OrdinalIgnoreCase)
                    || path.EndsWith("/" + matcher, StringComparison.OrdinalIgnoreCase);
            }

            try
            {
                return Regex.IsMatch(path, matcher, RegexOptions.IgnoreCase);
            }
            catch (Exception ex)
            {
                WarnOnce("invalid_regex_" + matcher, "invalid keypoint regex '" + matcher + "': " + ex.Message);
                return false;
            }
        }

        private static string ResolveKeyName(KeypointBinding binding)
        {
            string rawKind = binding.kind ?? string.Empty;
            if (!string.IsNullOrEmpty(rawKind))
            {
                return rawKind;
            }

            KeypointKind kind = binding.GetKind();
            return kind.ToString();
        }

        private void WarnOnce(string key, string message)
        {
            if (_warnedKeys.Contains(key))
            {
                return;
            }

            _warnedKeys.Add(key);
            Globals.Logger?.LogWarning("[live2d] " + message);
        }
    }
}
