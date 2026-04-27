import subprocess
import sys
import os
import socket
import threading

Port = 5000
Found_Devices = []
Lock = threading.Lock()

def Get_Local_Info():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    prefix = ".".join(ip.split(".")[:-1]) + "."
    return ip, prefix

def Try_Connect(IP):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.2)
        s.connect((IP, Port))
        s.close()
        with Lock:
            Found_Devices.append(IP)
            print(f"[NETWORK FOUND] Active device at: {IP}")
    except:
        pass

def Scan_Network():
    My_IP, Prefix = Get_Local_Info()
    print(f"[SCANNING] Your IP: {My_IP}")
    print(f"[SCANNING] Searching {Prefix}1 to {Prefix}254 for Port {Port}...")

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
        print("[SCANNING] No other active networks/devices found on Port 5000.")
    else:
        print(f"[SCANNING] Total devices found: {len(Found_Devices)}")
    print("-" * 40)

Scan_Network()

Base_Path = os.path.dirname(os.path.abspath(__file__))

RX_Path = os.path.join(Base_Path, "Files", "Python", "RX.py")
TX_Path = os.path.join(Base_Path, "Files", "Python", "TX.py")

Python_Path = sys.executable

print("Starting Blockchain... 🚀")

TX_Process = subprocess.Popen([Python_Path, TX_Path])
RX_Process = subprocess.Popen([Python_Path, RX_Path])

RX_Process.wait()
TX_Process.wait()