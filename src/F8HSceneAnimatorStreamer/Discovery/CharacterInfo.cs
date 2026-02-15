using System.Collections.Generic;
using UnityEngine;

namespace F8HSceneAnimatorStreamer.Discovery
{
    public sealed class CharacterInfo
    {
        public int CharacterId;
        public string CharacterName;
        public GameObject Root;
        public Animator Animator;
        public Animation Animation;
        public object Controller;
        public int FemaleIndex;
        public string ProfileId;
        public Dictionary<string, Transform> KeypointMap;
    }
}
