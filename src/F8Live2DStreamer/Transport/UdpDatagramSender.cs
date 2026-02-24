using System;
using System.Net;
using System.Net.Sockets;

namespace F8Live2DStreamer.Transport
{
    internal sealed class UdpDatagramSender : IDisposable
    {
        private readonly UdpClient _client;
        private readonly IPEndPoint _target;

        public UdpDatagramSender(string host, int port)
        {
            _target = new IPEndPoint(ResolveAddress(host), port);
            _client = new UdpClient();
        }

        public void Send(byte[] payload)
        {
            if (payload == null || payload.Length == 0)
            {
                return;
            }
            _client.Send(payload, payload.Length, _target);
        }

        public void Dispose()
        {
            _client.Close();
        }

        private static IPAddress ResolveAddress(string host)
        {
            IPAddress ip;
            if (IPAddress.TryParse(host, out ip))
            {
                return ip;
            }
            IPAddress[] all = Dns.GetHostAddresses(host);
            if (all != null && all.Length > 0)
            {
                return all[0];
            }
            return IPAddress.Loopback;
        }
    }
}
