using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Text.RegularExpressions;
using UnityEngine;

namespace F8HSceneAnimatorStreamer.Profiles
{
    internal sealed class ExpressionEvaluator
    {
        private const BindingFlags Flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        public object[] EvaluateObjects(object hookInstance, string expression)
        {
            if (string.IsNullOrEmpty(expression))
            {
                return new object[0];
            }

            string[] fallback = expression.Split(new[] { "??" }, StringSplitOptions.None);
            for (int i = 0; i < fallback.Length; i++)
            {
                object[] result = EvaluateSingle(hookInstance, ApplyTemplate(fallback[i].Trim(), hookInstance));
                if (result.Length > 0)
                {
                    return result;
                }
            }

            return new object[0];
        }

        public Transform[] EvaluateTransforms(object hookInstance, string expression)
        {
            object[] objects = EvaluateObjects(hookInstance, expression);
            var result = new List<Transform>(objects.Length);
            for (int i = 0; i < objects.Length; i++)
            {
                Transform transform = ToTransform(objects[i]);
                if (transform != null)
                {
                    result.Add(transform);
                }
            }
            return result.ToArray();
        }

        public Transform FindByPathOrName(Transform root, string pathOrName, bool useRegex)
        {
            if (root == null || string.IsNullOrEmpty(pathOrName))
            {
                return null;
            }

            Transform direct = root.Find(pathOrName);
            if (direct != null)
            {
                return direct;
            }

            Transform[] all = root.GetComponentsInChildren<Transform>(true);
            for (int i = 0; i < all.Length; i++)
            {
                Transform tf = all[i];
                if (tf == null)
                {
                    continue;
                }

                string fullPath = BuildPath(tf, root);
                if (!useRegex)
                {
                    if (string.Equals(tf.name, pathOrName, StringComparison.OrdinalIgnoreCase)
                        || string.Equals(fullPath, pathOrName, StringComparison.OrdinalIgnoreCase)
                        || fullPath.EndsWith("/" + pathOrName, StringComparison.OrdinalIgnoreCase))
                    {
                        return tf;
                    }
                    continue;
                }

                try
                {
                    if (Regex.IsMatch(tf.name, pathOrName)
                        || Regex.IsMatch(fullPath, pathOrName))
                    {
                        return tf;
                    }
                }
                catch
                {
                    return null;
                }
            }

            GameObject global = GameObject.Find(pathOrName);
            return global != null ? global.transform : null;
        }

        private object[] EvaluateSingle(object hookInstance, string expression)
        {
            string[] arrows = expression.Split(new[] { "->" }, StringSplitOptions.None);
            object[] current = EvaluateBase(hookInstance, arrows[0].Trim());
            for (int i = 1; i < arrows.Length; i++)
            {
                current = ApplyArrowStep(current, arrows[i].Trim());
                if (current.Length == 0)
                {
                    break;
                }
            }
            return current;
        }

        private object[] EvaluateBase(object hookInstance, string expression)
        {
            const string childrenPrefix = " children prefix ";
            int prefixIndex = expression.IndexOf(childrenPrefix, StringComparison.Ordinal);
            if (prefixIndex >= 0)
            {
                string left = expression.Substring(0, prefixIndex).Trim();
                string prefix = expression.Substring(prefixIndex + childrenPrefix.Length).Trim();
                prefix = prefix.Replace("[*]", string.Empty);
                object[] seed = EvaluateBase(hookInstance, left);
                var children = new List<object>();
                for (int i = 0; i < seed.Length; i++)
                {
                    Transform tf = ToTransform(seed[i]);
                    if (tf == null)
                    {
                        continue;
                    }
                    IEnumerator iterator = tf.GetEnumerator();
                    while (iterator.MoveNext())
                    {
                        Transform child = iterator.Current as Transform;
                        if (child != null && child.name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        {
                            children.Add(child);
                        }
                    }
                }
                return children.ToArray();
            }

            const string pathExact = "path exact ";
            if (expression.StartsWith(pathExact, StringComparison.OrdinalIgnoreCase))
            {
                string path = expression.Substring(pathExact.Length).Trim();
                GameObject found = GameObject.Find(path);
                if (found == null)
                {
                    return new object[0];
                }
                return new object[] { found.transform };
            }

            return EvaluateReflection(hookInstance, expression);
        }

        private static object[] ApplyArrowStep(object[] current, string step)
        {
            if (string.IsNullOrEmpty(step))
            {
                return current;
            }

            string childName = step;
            int? childIndex = null;
            int bracket = step.LastIndexOf('[');
            if (bracket >= 0 && step.EndsWith("]", StringComparison.Ordinal))
            {
                string indexText = step.Substring(bracket + 1, step.Length - bracket - 2);
                int parsed;
                if (int.TryParse(indexText, out parsed))
                {
                    childIndex = parsed;
                    childName = step.Substring(0, bracket);
                }
            }

            var next = new List<object>();
            for (int i = 0; i < current.Length; i++)
            {
                Transform tf = ToTransform(current[i]);
                if (tf == null)
                {
                    continue;
                }

                Transform target = tf;
                if (!string.IsNullOrEmpty(childName))
                {
                    target = tf.Find(childName);
                    if (target == null)
                    {
                        target = FindDeep(tf, childName);
                    }
                }

                if (target == null)
                {
                    continue;
                }

                if (childIndex.HasValue)
                {
                    int index = childIndex.Value;
                    if (index >= 0 && index < target.childCount)
                    {
                        next.Add(target.GetChild(index));
                    }
                    continue;
                }

                next.Add(target);
            }

            return next.ToArray();
        }

        private static object[] EvaluateReflection(object hookInstance, string expression)
        {
            string trimmed = expression.Trim();
            if (trimmed.Length == 0)
            {
                return new object[0];
            }

            object[] current;
            if (string.Equals(trimmed, "instance", StringComparison.OrdinalIgnoreCase)
                || string.Equals(trimmed, "self", StringComparison.OrdinalIgnoreCase))
            {
                current = hookInstance == null ? new object[0] : new object[] { hookInstance };
                return current;
            }

            if (trimmed.StartsWith("instance.", StringComparison.OrdinalIgnoreCase)
                || trimmed.StartsWith("self.", StringComparison.OrdinalIgnoreCase))
            {
                trimmed = trimmed.Substring(trimmed.IndexOf('.') + 1);
                current = hookInstance == null ? new object[0] : new object[] { hookInstance };
            }
            else
            {
                current = hookInstance == null ? new object[0] : new object[] { hookInstance };
            }

            string[] segments = trimmed.Split('.');
            for (int i = 0; i < segments.Length; i++)
            {
                string segment = segments[i].Trim();
                if (segment.Length == 0)
                {
                    continue;
                }

                bool expand = segment.EndsWith("[]", StringComparison.Ordinal);
                if (expand)
                {
                    segment = segment.Substring(0, segment.Length - 2);
                }

                bool explicitMethod = segment.EndsWith("()", StringComparison.Ordinal);
                if (explicitMethod)
                {
                    segment = segment.Substring(0, segment.Length - 2);
                }

                var next = new List<object>();
                for (int j = 0; j < current.Length; j++)
                {
                    object value = ReadMember(current[j], segment, explicitMethod);
                    if (value == null)
                    {
                        continue;
                    }

                    if (expand)
                    {
                        IEnumerable enumerable = value as IEnumerable;
                        if (enumerable == null || value is string)
                        {
                            continue;
                        }

                        foreach (object item in enumerable)
                        {
                            if (item != null)
                            {
                                next.Add(item);
                            }
                        }
                    }
                    else
                    {
                        next.Add(value);
                    }
                }

                current = next.ToArray();
                if (current.Length == 0)
                {
                    break;
                }
            }

            return current;
        }

        private static object ReadMember(object source, string memberName, bool explicitMethod)
        {
            if (source == null || string.IsNullOrEmpty(memberName))
            {
                return null;
            }

            Type type = source.GetType();
            if (!explicitMethod)
            {
                PropertyInfo property = type.GetProperty(memberName, Flags);
                if (property != null)
                {
                    try { return property.GetValue(source, null); } catch { }
                }

                FieldInfo field = type.GetField(memberName, Flags);
                if (field != null)
                {
                    try { return field.GetValue(source); } catch { }
                }
            }

            MethodInfo method = type.GetMethod(memberName, Flags, null, Type.EmptyTypes, null);
            if (method != null)
            {
                try { return method.Invoke(source, null); } catch { }
            }

            if (!explicitMethod)
            {
                method = type.GetMethod(memberName + "()", Flags, null, Type.EmptyTypes, null);
                if (method != null)
                {
                    try { return method.Invoke(source, null); } catch { }
                }
            }

            return null;
        }

        private static Transform ToTransform(object value)
        {
            if (value == null)
            {
                return null;
            }

            Transform transform = value as Transform;
            if (transform != null)
            {
                return transform;
            }

            GameObject gameObject = value as GameObject;
            if (gameObject != null)
            {
                return gameObject.transform;
            }

            Component component = value as Component;
            if (component != null)
            {
                return component.transform;
            }

            return null;
        }

        private static string ApplyTemplate(string expression, object hookInstance)
        {
            if (string.IsNullOrEmpty(expression) || hookInstance == null)
            {
                return expression;
            }

            const string token = "${instance.name}";
            if (!expression.Contains(token))
            {
                return expression;
            }

            string name = hookInstance.ToString();
            UnityEngine.Object unityObject = hookInstance as UnityEngine.Object;
            if (unityObject != null)
            {
                name = unityObject.name;
            }

            return expression.Replace(token, name ?? string.Empty);
        }

        private static Transform FindDeep(Transform root, string pathOrName)
        {
            Transform[] all = root.GetComponentsInChildren<Transform>(true);
            for (int i = 0; i < all.Length; i++)
            {
                Transform tf = all[i];
                if (tf == null)
                {
                    continue;
                }
                if (string.Equals(tf.name, pathOrName, StringComparison.OrdinalIgnoreCase)
                    || BuildPath(tf, root).EndsWith("/" + pathOrName, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(BuildPath(tf, root), pathOrName, StringComparison.OrdinalIgnoreCase))
                {
                    return tf;
                }
            }
            return null;
        }

        private static string BuildPath(Transform transform, Transform root)
        {
            string path = transform.name;
            Transform current = transform.parent;
            while (current != null)
            {
                path = current.name + "/" + path;
                if (current == root)
                {
                    break;
                }
                current = current.parent;
            }
            return path;
        }
    }
}
