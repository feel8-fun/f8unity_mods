using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using F8Live2DStreamer.Sampling;

namespace F8Live2DStreamer.Protocol
{
    internal sealed class Live2DDrawablePacketEncoder
    {
        private const ushort ExtVersion = 1;
        private static readonly byte[] TrailerMagic = Encoding.ASCII.GetBytes("LMEX");
        private static readonly Encoding Utf8 = Encoding.UTF8;

        private struct Chunk
        {
            public int Start;
            public int Count;
        }

        public byte[][] EncodeChunks(Live2DCharacterFrame frame, string schema, int maxPayloadBytes)
        {
            if (frame.Drawables == null || frame.Drawables.Length == 0)
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

        private List<Chunk> BuildChunks(Live2DCharacterFrame frame, string modelName, string schema, int maxBytes)
        {
            int trailerSize = GetTrailerSize();
            int headerSize = GetHeaderSize(modelName, schema);
            int offset = headerSize;
            int start = 0;
            int count = 0;
            var chunks = new List<Chunk>();

            for (int i = 0; i < frame.Drawables.Length; i++)
            {
                int sampleSize = GetDrawableSize(offset, frame.Drawables[i]);
                bool overflow = count > 0 && offset + sampleSize + trailerSize > maxBytes;
                if (overflow)
                {
                    chunks.Add(new Chunk { Start = start, Count = count });
                    start = i;
                    count = 0;
                    offset = headerSize;
                    sampleSize = GetDrawableSize(offset, frame.Drawables[i]);
                }

                offset += sampleSize;
                count++;
            }

            if (count > 0)
            {
                chunks.Add(new Chunk { Start = start, Count = count });
            }

            return chunks;
        }

        private byte[] EncodePacket(Live2DCharacterFrame frame, string modelName, string schema, Chunk chunk,
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
                    DrawableSample sample = frame.Drawables[chunk.Start + i];
                    WriteAlignedString(writer, sample.DrawablePath);
                    writer.Write(sample.CenterX);
                    writer.Write(sample.CenterY);
                    writer.Write(sample.CenterZ);
                    writer.Write(sample.ExtentsX);
                    writer.Write(sample.ExtentsY);
                    writer.Write(sample.ExtentsZ);
                    writer.Write(sample.Opacity);
                    writer.Write(sample.DrawOrder);
                    writer.Write(sample.Visible);
                }

                WriteTrailer(writer, frame, chunkIndex, chunkCount);
                writer.Flush();
                return stream.ToArray();
            }
        }

        private static void WriteTrailer(BinaryWriter writer, Live2DCharacterFrame frame, int chunkIndex, int chunkCount)
        {
            writer.Write(TrailerMagic);
            writer.Write(ExtVersion);
            writer.Write(frame.FrameId);
            writer.Write(chunkIndex);
            writer.Write(chunkCount);
            writer.Write(frame.Drawables != null ? frame.Drawables.Length : 0);
            writer.Write(frame.CharacterId);
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

        private static int GetDrawableSize(int offset, DrawableSample sample)
        {
            int size = GetAlignedStringSize(offset, sample.DrawablePath);
            size += 7 * 4;
            size += 4;
            size += 4;
            return size;
        }

        private static int GetTrailerSize()
        {
            return 4 + 2 + 8 + 4 + 4 + 4 + 4;
        }

        private static int GetAlignedStringSize(int offset, string value)
        {
            int raw = Utf8.GetByteCount(value ?? string.Empty) + 1;
            int padding = (4 - ((offset + raw) & 0x03)) & 0x03;
            return raw + padding;
        }
    }
}
