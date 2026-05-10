from sys import argv
import sys
import subprocess
import os

cwd = os.path.abspath(os.path.dirname(__file__))

argv = argv[1:]
if len(argv) != 2:
    print(f"usage: python3 {__file__} MIN_ID(int) MAX_ID(int)")
    print("goes in the range of [MIN_ID, MAX_ID)")
    sys.exit()

min_id = int(argv[0])
max_id = int(argv[1])
for i in range(min_id, max_id):
    subprocess.Popen([sys.executable, "./game.py", str(i)], cwd=cwd)
