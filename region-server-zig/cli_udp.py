import socket
import os
from random import randint

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

data = bytearray((str(os.getpid()) + " hedawllo world\n").encode())

while True:
    data[-randint(2, 5)] = randint(ord("a"), ord("z"))
    msg = len(data).to_bytes(4, "little") + data
    s.sendto(msg, ("127.0.0.1", 8826))
