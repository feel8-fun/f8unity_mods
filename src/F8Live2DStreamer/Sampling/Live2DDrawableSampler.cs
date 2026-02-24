using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.RegularExpressions;
using F8Live2DStreamer.Discovery;
using F8Live2DStreamer.NonPortable;
using F8Live2DStreamer.Profiles;
using UnityEngine;

namespace F8Live2DStreamer.Sampling
{
    internal sealed class Live2DDrawableSampler : MonoBehaviour, ILive2DDrawableSampler
    {
        private const BindingFlags Flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        private readonly HashSet<string> _warnedKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        public DrawableSample[] Sample(Live2DCharacterInfo character, GameProfile profile)
        {
            if (character == null || character.Root == null || profile == null)
            {
                return new DrawableSample[0];
            }

            Transform root = character.Root.transform;
            var output = new List<DrawableSample>(64);
            var seen = new HashSet<int>();

            Component[] allComponents = root.GetComponentsInChildren<Component>(true);
            bool foundCubismDrawable = false;
            for (int i = 0; i < allComponents.Length; i++)
            {
                Component component = allComponents[i];
                if (component == null)
                {
                    continue;
                }

                string typeName = component.GetType().Name;
                if (typeName.IndexOf("CubismDrawable", StringComparison.OrdinalIgnoreCase) < 0)
                {
                    continue;
                }

                foundCubismDrawable = true;
                AppendDrawable(root, component, ResolveRenderer(component), profile, output, seen);
            }

            if (!foundCubismDrawable)
            {
                Renderer[] renderers = root.GetComponentsInChildren<Renderer>(true);
                for (int i = 0; i < renderers.Length; i++)
                {
                    Renderer renderer = renderers[i];
                    if (renderer == null)
                    {
                        continue;
                    }

                    AppendDrawable(root, renderer, renderer, profile, output, seen);
                }
            }

            output.Sort((a, b) => string.Compare(a.DrawablePath, b.DrawablePath, StringComparison.Ordinal));
            return output.ToArray();
        }

        private void AppendDrawable(
            Transform root,
            Component source,
            Renderer renderer,
            GameProfile profile,
            IList<DrawableSample> output,
            HashSet<int> seen)
        {
            if (renderer == null)
            {
                return;
            }

            int rendererId = renderer.GetInstanceID();
            if (seen.Contains(rendererId))
            {
                return;
            }
            seen.Add(rendererId);

            if (profile.activeOnly && !renderer.gameObject.activeInHierarchy)
            {
                return;
            }

            Bounds bounds = renderer.bounds;
            float maxExtent = Mathf.Max(Mathf.Abs(bounds.extents.x), Mathf.Abs(bounds.extents.y), Mathf.Abs(bounds.extents.z));
            if (maxExtent < Mathf.Max(0f, profile.minBoundsExtent))
            {
                return;
            }

            string path = BuildRelativePath(root, renderer.transform);
            if (!IsNameAllowed(path, profile))
            {
                return;
            }

            float opacity = ReadFloat(source, "Opacity")
                ?? ReadFloat(source, "opacity")
                ?? ReadFloat(source, "Alpha")
                ?? ReadFloat(source, "alpha")
                ?? ReadMaterialOpacity(renderer)
                ?? 1f;

            int drawOrder = ReadInt(source, "RenderOrder")
                ?? ReadInt(source, "DrawOrder")
                ?? ReadInt(source, "renderOrder")
                ?? ReadInt(source, "drawOrder")
                ?? renderer.sortingOrder;

            int visible = renderer.enabled && renderer.gameObject.activeInHierarchy ? 1 : 0;

            output.Add(new DrawableSample
            {
                DrawablePath = path,
                CenterX = bounds.center.x,
                CenterY = bounds.center.y,
                CenterZ = bounds.center.z,
                ExtentsX = bounds.extents.x,
                ExtentsY = bounds.extents.y,
                ExtentsZ = bounds.extents.z,
                Opacity = opacity,
                DrawOrder = drawOrder,
                Visible = visible
            });
        }

        private bool IsNameAllowed(string path, GameProfile profile)
        {
            if (!string.IsNullOrEmpty(profile.drawableNameIncludeRegex)
                && !SafeRegexMatch(path, profile.drawableNameIncludeRegex, "include"))
            {
                return false;
            }

            if (!string.IsNullOrEmpty(profile.drawableNameExcludeRegex)
                && SafeRegexMatch(path, profile.drawableNameExcludeRegex, "exclude"))
            {
                return false;
            }

            return true;
        }

        private bool SafeRegexMatch(string text, string pattern, string kind)
        {
            try
            {
                return Regex.IsMatch(text ?? string.Empty, pattern, RegexOptions.IgnoreCase);
            }
            catch (Exception ex)
            {
                WarnOnce("regex_" + kind + "_" + pattern, "invalid " + kind + " regex '" + pattern + "': " + ex.Message);
                return false;
            }
        }

        private static Renderer ResolveRenderer(Component component)
        {
            if (component == null)
            {
                return null;
            }

            Renderer direct = component as Renderer;
            if (direct != null)
            {
                return direct;
            }

            Renderer attached = component.GetComponent<Renderer>();
            if (attached != null)
            {
                return attached;
            }

            object fromProperty = ReadMember(component, "Renderer");
            return fromProperty as Renderer;
        }

        private float? ReadMaterialOpacity(Renderer renderer)
        {
            if (renderer == null)
            {
                return null;
            }

            try
            {
                Material material = renderer.sharedMaterial;
                if (material != null)
                {
                    return material.color.a;
                }
            }
            catch (Exception ex)
            {
                WarnOnce("material_opacity", "failed to read material opacity: " + ex.Message);
            }

            return null;
        }

        private float? ReadFloat(Component source, string member)
        {
            object value = ReadMember(source, member);
            if (value == null)
            {
                return null;
            }

            try
            {
                if (value is float f)
                {
                    return f;
                }
                if (value is double d)
                {
                    return (float)d;
                }
                if (value is int i)
                {
                    return i;
                }
                if (value is long l)
                {
                    return l;
                }
                float parsed;
                if (float.TryParse(value.ToString(), out parsed))
                {
                    return parsed;
                }
            }
            catch
            {
            }

            return null;
        }

        private int? ReadInt(Component source, string member)
        {
            object value = ReadMember(source, member);
            if (value == null)
            {
                return null;
            }

            try
            {
                if (value is int i)
                {
                    return i;
                }
                if (value is short s)
                {
                    return s;
                }
                if (value is long l)
                {
                    return (int)l;
                }
                if (value is float f)
                {
                    return (int)f;
                }
                if (value is double d)
                {
                    return (int)d;
                }
                int parsed;
                if (int.TryParse(value.ToString(), out parsed))
                {
                    return parsed;
                }
            }
            catch
            {
            }

            return null;
        }

        private static object ReadMember(object source, string member)
        {
            if (source == null || string.IsNullOrEmpty(member))
            {
                return null;
            }

            Type type = source.GetType();
            PropertyInfo property = type.GetProperty(member, Flags);
            if (property != null)
            {
                try
                {
                    return property.GetValue(source, null);
                }
                catch
                {
                }
            }

            FieldInfo field = type.GetField(member, Flags);
            if (field != null)
            {
                try
                {
                    return field.GetValue(source);
                }
                catch
                {
                }
            }

            return null;
        }

        private static string BuildRelativePath(Transform root, Transform child)
        {
            if (root == null || child == null)
            {
                return string.Empty;
            }

            if (root == child)
            {
                return root.name;
            }

            var segments = new List<string>();
            Transform current = child;
            while (current != null && current != root)
            {
                segments.Add(current.name);
                current = current.parent;
            }

            segments.Add(root.name);
            segments.Reverse();
            return string.Join("/", segments.ToArray());
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
