import subprocess
import sys
import os

Base_Path = os.path.dirname(os.path.abspath(__file__))

RX_Path = os.path.join(Base_Path, "Files", "Python", "RX.py")
TX_Path = os.path.join(Base_Path, "Files", "Python", "TX.py")

Python_Path = sys.executable

TX_Process = subprocess.Popen([Python_Path, TX_Path])
RX_Process = subprocess.Popen([Python_Path, RX_Path])

print("Starting... 🚀")

RX_Process.wait()
TX_Process.wait()