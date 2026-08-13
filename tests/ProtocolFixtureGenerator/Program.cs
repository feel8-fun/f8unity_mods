using System;
using System.IO;
using F8SkeletonStreamer.Protocol;
using F8SkeletonStreamer.Sampling;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length != 1 || string.IsNullOrWhiteSpace(args[0]))
        {
            Console.Error.WriteLine("Usage: ProtocolFixtureGenerator <output.bin>");
            return 2;
        }

        string outputPath = Path.GetFullPath(args[0]);
        string outputDirectory = Path.GetDirectoryName(outputPath);
        if (!string.IsNullOrEmpty(outputDirectory))
        {
            Directory.CreateDirectory(outputDirectory);
        }

        CharacterFrame frame = new CharacterFrame
        {
            FrameId = 42UL,
            TimestampMs = 1720000000123L,
            CharacterId = 1234,
            CharacterName = "Alice",
            ProfileId = "hs2",
            Role = "Female",
            RoleIndex = 0,
            ExporterVersion = "0.2.0",
            Bones = new[]
            {
                new BoneSample
                {
                    BonePath = "FemaleRoot",
                    X = 1.25f,
                    Y = -2.5f,
                    Z = 3.75f,
                    Qw = 1.0f,
                    Qx = 0.0f,
                    Qy = 0.0f,
                    Qz = 0.0f,
                },
                new BoneSample
                {
                    BonePath = "Vagina",
                    X = 0.1f,
                    Y = 0.2f,
                    Z = 0.3f,
                    Qw = 0.70710677f,
                    Qx = 0.0f,
                    Qy = 0.70710677f,
                    Qz = 0.0f,
                },
            },
            HasAnimationContext = true,
            NormalizedTime = 0.625f,
            LayerIndex = 1,
            ClipName = "Loop",
            PoseKey = "fixture_pose",
        };

        SkeletonPacketEncoder encoder = new SkeletonPacketEncoder();
        byte[][] packets = encoder.EncodeChunks(frame, "unity.keypoints.realtime.v1", 65507);
        if (packets.Length != 1)
        {
            Console.Error.WriteLine("Expected one fixture packet, got " + packets.Length);
            return 3;
        }

        File.WriteAllBytes(outputPath, packets[0]);
        Console.WriteLine(outputPath);
        return 0;
    }
}
