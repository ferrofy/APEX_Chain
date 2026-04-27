import subprocess
import sys
import os
import socket
import threading
import time

Port = 5000
Found_Devices = []
Lock = threading.Lock()

def Get_Local_Info():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        IP = s.getsockname()[0]
    except:
        IP = "127.0.0.1"
    finally:
        s.close()
    Prefix = ".".join(IP.split(".")[:-1]) + "."
    return IP, Prefix

def Try_Connect(IP):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        s.connect((IP, Port))
        s.close()
        with Lock:
            Found_Devices.append(IP)
            print(f"[Network Found] Active Node At: {IP}")
    except:
        pass

def Scan_Network():
    My_IP, Prefix = Get_Local_Info()
    print(f"[Scanning] Your IP: {My_IP}")
    print(f"[Scanning] Searching {Prefix}1 To {Prefix}254 On Port {Port}...")

    Threads = []
    for i in range(1, 255):
        IP = f"{Prefix}{i}"

        if IP == My_IP or IP == "127.0.0.1":
            continue

        t = threading.Thread(target=Try_Connect, args=(IP,))
        Threads.append(t)
        t.start()

    for t in Threads:
        t.join()

    if not Found_Devices:
        print("[Scanning] No Active Blockchain Nodes Found On The Network.")
    else:
        print(f"[Scanning] Total Active Nodes Found: {len(Found_Devices)}")
    print("-" * 50)

    return len(Found_Devices) > 0

Base_Path = os.path.dirname(os.path.abspath(__file__))
RX_Path = os.path.join(Base_Path, "Files", "Python", "RX.py")
TX_Path = os.path.join(Base_Path, "Files", "Python", "TX.py")
Python_Path = sys.executable

print("=" * 50)
print("   FerroFy Blockchain Node Launcher 🚀")
print("=" * 50)

Node_Found = Scan_Network()

if Node_Found:
    print("[Mode] Receiver (RX) Mode - Connecting To Existing Node...")
    time.sleep(1)
    Process = subprocess.Popen([Python_Path, RX_Path])
    Process.wait()
else:
    print("[Mode] Transmitter (TX) Mode - Starting As Blockchain Origin Node...")
    time.sleep(1)
    Process = subprocess.Popen([Python_Path, TX_Path])
    Process.wait()