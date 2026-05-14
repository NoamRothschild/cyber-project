import socket
import os
import protobuf.region_net_pb2 as region_net

HOST = ("127.0.0.1", 8826)
MAX_PAYLOAD_LEN = 512
MAX_FRAME_LEN = 4 + MAX_PAYLOAD_LEN


class Connections:
    def __init__(self):
        self.udp_s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.tcp_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_s.connect(("127.0.0.1", 8826))

    def write_udp(self, data: bytes):
        bdata = len(data).to_bytes(4, "little") + data
        self.udp_s.sendto(bdata, HOST)

    def write_tcp(self, data: bytes):
        bdata = len(data).to_bytes(4, "little") + data
        self.tcp_s.send(bdata)

    def read_udp(self) -> bytes:
        datagram, _ = self.udp_s.recvfrom(MAX_FRAME_LEN)
        payload_len = int.from_bytes(datagram[:4], "little")
        return datagram[4 : 4 + min(payload_len, MAX_PAYLOAD_LEN)]

    def read_tcp(self) -> bytes:
        hdr = self._read_exact(self.tcp_s, 4)
        payload_len = int.from_bytes(hdr, "little")
        data = self._read_exact(self.tcp_s, payload_len % (MAX_PAYLOAD_LEN + 1))
        return data

    @staticmethod
    def _read_exact(sock: socket.socket, n: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < n:
            chunk = sock.recv(n - len(chunks))
            if not chunk:
                raise RuntimeError("socket closed during read")
            chunks.extend(chunk)
        return bytes(chunks)

    def do_handshake(self):
        session_id = os.getpid()
        pkt = region_net.HandshakeStart(session_id=session_id)
        print(f"sent: {pkt}")

        # will create the entry for the client in the server
        self.write_tcp(pkt.SerializeToString())
        tc = self.read_tcp()
        resp = region_net.HandshakeStart.FromString(tc)
        print(f"tcp got ({len(tc)}): {resp}")
        user_id = resp.user_id
        assert user_id != 0
        assert resp.kind == region_net.HandshakeStart.SERVER_OK

        # will extend with another capability to the client, adding the option to use udp
        self.write_udp(pkt.SerializeToString())
        print(f"udp got: {resp}")
        resp = region_net.HandshakeStart.FromString(self.read_udp())
        assert resp.user_id == user_id
        assert resp.kind == region_net.HandshakeStart.SERVER_OK


conn = Connections()
try:
    conn.do_handshake()

    pkt = region_net.RegionUpdate(
        location_block=region_net.LocationBlock(x=5, y=5), sender_id=1
    )
    conn.write_tcp(pkt.SerializeToString())
    pkt.location_block.x += 300
    conn.write_udp(pkt.SerializeToString())


finally:
    # will remove the client object from the server, also means close udp tunnel if was opened
    conn.tcp_s.close()
