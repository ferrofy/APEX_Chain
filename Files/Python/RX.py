import socket
import os
import threading
import time

Port = 5000
Folder = "Blocks"

def Init_Folder():
    if not os.path.exists(Folder):
        os.makedirs(Folder)

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

def Scan_And_Connect():
    My_IP, Prefix = Get_Local_Info()
    Sockets = []
    Lock = threading.Lock()

    def Try_Connect(IP):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect((IP, Port))
            
            s.settimeout(2.0)
            
            Server_Greeting = s.recv(1024).decode()
            if Server_Greeting != "Mine_RX":
                s.close()
                return
            
            s.send("Mine_TX".encode())
            
            s.settimeout(None)
            
            with Lock:
                Sockets.append((IP, s))
                print(f"[VERIFIED & CONNECTED] {IP}")
        except:
            pass

    print("[SCANNING] 15-second window...")
    Start_Time = time.time()
    
    while time.time() - Start_Time < 15:
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

        if len(Sockets) > 0:
            break
            
        time.sleep(0.5)

    return Sockets

def Save_File(File_Name, Content):
    Path = os.path.join(Folder, File_Name)
    with open(Path, "w") as f:
        f.write(Content)

def Receive_Loop(Sock, IP):
    while True:
        try:
            Data = Sock.recv(8192).decode()
            if not Data:
                break

            File_Name, Content = Data.split("|")
            Save_File(File_Name, Content)
            print(f"[RECEIVED FROM {IP}] {File_Name}")

        except:
            print(f"[ERROR] Connection Lost to {IP}")
            break

def Send_Loop(Sock, IP):
    Index = 1
    while True:
        try:
            File_Name = f"Client_File_{Index}_{IP}.txt"
            Content = f"Client File {Index} to {IP}"
            Data = f"{File_Name}|{Content}"
            
            Sock.send(Data.encode())
            print(f"[SENT TO {IP}] {File_Name}")
            Index += 1
            time.sleep(15)
            
        except:
            break

def Start_Client():
    Init_Folder()

    while True:
        Connections = Scan_And_Connect()

        if len(Connections) >= 1:
            print(f"[SUCCESS] Established {len(Connections)} verified connection(s).")
            
            for IP, Sock in Connections:
                threading.Thread(target=Receive_Loop, args=(Sock, IP)).start()
                threading.Thread(target=Send_Loop, args=(Sock, IP)).start()
            break
        else:
            print("[TIMEOUT] No verified servers found. Sleeping 60 seconds...")
            time.sleep(60)

Start_Client()