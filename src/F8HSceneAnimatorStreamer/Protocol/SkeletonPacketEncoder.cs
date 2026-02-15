using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using F8HSceneAnimatorStreamer.Sampling;

namespace F8HSceneAnimatorStreamer.Protocol
{
    internal sealed class SkeletonPacketEncoder
    {
        private const ushort ExtVersion = 1;
        private static readonly byte[] TrailerMagic = Encoding.ASCII.GetBytes("LMEX");
        private static readonly byte[] AnimMagic = Encoding.ASCII.GetBytes("ANIM");
        private static readonly Encoding Utf8 = Encoding.UTF8;

        private struct Chunk
        {
            public int Start;
            public int Count;
        }

        public byte[][] EncodeChunks(CharacterFrame frame, string schema, int maxPayloadBytes)
        {
            if (frame.Bones == null || frame.Bones.Length == 0)
            {
                return new byte[0][];
            }
            if (maxPayloadBytes < 256)
            {
                maxPayloadBytes = 256;
            }

            string modelName = frame.CharacterId + "|" + (frame.CharacterName ?? string.Empty);
            List<Chunk> chunks = BuildChunks(frame, modelName, schema, maxPayloadBytes);
            var packets = new byte[chunks.Count][];
            for (int i = 0; i < chunks.Count; i++)
            {
                packets[i] = EncodePacket(frame, modelName, schema, chunks[i], i, chunks.Count);
            }
            return packets;
        }

        private List<Chunk> BuildChunks(CharacterFrame frame, string modelName, string schema, int maxBytes)
        {
            int trailerSize = GetTrailerSize(frame);
            int headerSize = GetHeaderSize(modelName, schema);
            int offset = headerSize;
            int start = 0;
            int count = 0;
            var chunks = new List<Chunk>();

            for (int i = 0; i < frame.Bones.Length; i++)
            {
                int nextBoneSize = GetBoneSize(offset, frame.Bones[i]);
                bool overflow = count > 0 && offset + nextBoneSize + trailerSize > maxBytes;
                if (overflow)
                {
                    chunks.Add(new Chunk { Start = start, Count = count });
                    start = i;
                    count = 0;
                    offset = headerSize;
                    nextBoneSize = GetBoneSize(offset, frame.Bones[i]);
                }

                offset += nextBoneSize;
                count++;
            }

            if (count > 0)
            {
                chunks.Add(new Chunk { Start = start, Count = count });
            }

            return chunks;
        }

        private byte[] EncodePacket(CharacterFrame frame, string modelName, string schema, Chunk chunk,
            int chunkIndex, int chunkCount)
        {
            using (var stream = new MemoryStream())
            using (var writer = new BinaryWriter(stream, Utf8))
            {
                WriteAlignedString(writer, modelName);
                writer.Write((ulong)Math.Max(0L, frame.TimestampMs));
                WriteAlignedString(writer, schema);
                writer.Write(chunk.Count);
                for (int i = 0; i < chunk.Count; i++)
                {
                    BoneSample bone = frame.Bones[chunk.Start + i];
                    WriteAlignedString(writer, bone.BonePath);
                    writer.Write(bone.X);
                    writer.Write(bone.Y);
                    writer.Write(bone.Z);
                    writer.Write(bone.Qw);
                    writer.Write(bone.Qx);
                    writer.Write(bone.Qy);
                    writer.Write(bone.Qz);
                }

                WriteTrailer(writer, frame, chunkIndex, chunkCount);
                writer.Flush();
                return stream.ToArray();
            }
        }

        private void WriteTrailer(BinaryWriter writer, CharacterFrame frame, int chunkIndex, int chunkCount)
        {
            writer.Write(TrailerMagic);
            writer.Write(ExtVersion);
            writer.Write(frame.FrameId);
            writer.Write(chunkIndex);
            writer.Write(chunkCount);
            writer.Write(frame.Bones != null ? frame.Bones.Length : 0);
            writer.Write(frame.CharacterId);

            if (!frame.HasAnimationContext)
            {
                return;
            }

            writer.Write(AnimMagic);
            writer.Write(frame.NormalizedTime);
            writer.Write(frame.LayerIndex);
            WriteAlignedString(writer, frame.ClipName ?? string.Empty);
            WriteAlignedString(writer, frame.PoseKey ?? string.Empty);
        }

        private static void WriteAlignedString(BinaryWriter writer, string value)
        {
            byte[] bytes = Utf8.GetBytes(value ?? string.Empty);
            writer.Write(bytes);
            writer.Write((byte)0);
            int padding = (int)((4 - (writer.BaseStream.Position & 0x03)) & 0x03);
            for (int i = 0; i < padding; i++)
            {
                writer.Write((byte)0);
            }
        }

        private static int GetHeaderSize(string modelName, string schema)
        {
            int offset = 0;
            offset += GetAlignedStringSize(offset, modelName);
            offset += 8;
            offset += GetAlignedStringSize(offset, schema);
            offset += 4;
            return offset;
        }

        private static int GetBoneSize(int offset, BoneSample sample)
        {
            int size = GetAlignedStringSize(offset, sample.BonePath);
            size += 7 * 4;
            return size;
        }

        private static int GetTrailerSize(CharacterFrame frame)
        {
            int fixedTrailer = 4 + 2 + 8 + 4 + 4 + 4 + 4;
            if (!frame.HasAnimationContext)
            {
                return fixedTrailer;
            }

            int offset = fixedTrailer;
            offset += 4;
            offset += 4;
            offset += 4;
            offset += GetAlignedStringSize(offset, frame.ClipName ?? string.Empty);
            offset += GetAlignedStringSize(offset, frame.PoseKey ?? string.Empty);
            return offset;
        }

        private static int GetAlignedStringSize(int offset, string value)
        {
            int raw = Utf8.GetByteCount(value ?? string.Empty) + 1;
            int padding = (4 - ((offset + raw) & 0x03)) & 0x03;
            return raw + padding;
        }
    }
}
