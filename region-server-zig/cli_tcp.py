import socket
import os

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 8826))

data = (str(os.getpid()) + " hedawllo world\n").encode()

msg = len(data).to_bytes(4, "little") + data
while True:
    s.send(msg)
