import socket
import os
import threading
import time
import json
import hashlib

Port = 5000
Folder = "Blocks"

def Init_Folder():
    if not os.path.exists(Folder):
        os.makedirs(Folder)

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

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

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Validate_Block(Block, Previous_Block):
    Expected_Index = Previous_Block["Index"] + 1
    if Block["Index"] != Expected_Index:
        return False, f"Index Mismatch: Expected {Expected_Index}, Got {Block['Index']}"

    if Block["Previous_Hash"] != Previous_Block["Hash"]:
        return False, "Previous Hash Mismatch"

    Recomputed = Compute_Block_Hash(
        Block["Index"], Block["Timestamp"], Block["Data"], Block["Previous_Hash"]
    )
    if Recomputed != Block["Hash"]:
        return False, "Block Hash Invalid"

    return True, "Valid"

def Save_Block(Block):
    File_Name = f"{Block['Index']}.json"
    Path = os.path.join(Folder, File_Name)
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return File_Name

def Recv_Length_Prefixed(Sock):
    Header = b""
    while len(Header) < 4:
        Chunk = Sock.recv(4 - len(Header))
        if not Chunk:
            return None
        Header += Chunk

    Length = int.from_bytes(Header, byteorder="big")

    Data = b""
    while len(Data) < Length:
        Chunk = Sock.recv(min(8192, Length - len(Data)))
        if not Chunk:
            return None
        Data += Chunk

    return Data

def Receive_Loop(Sock, IP, Chain):
    while True:
        try:
            Raw = Recv_Length_Prefixed(Sock)
            if Raw is None:
                print(f"[Disconnected] Server {IP} Closed Connection")
                break

            Block = json.loads(Raw.decode())

            if len(Chain) == 0:
                Chain.append(Block)
                File_Name = Save_Block(Block)
                print(f"[Received] {File_Name} | Hash: {Block['Hash'][:16]}... [Root Block]")
            else:
                Valid, Reason = Validate_Block(Block, Chain[-1])
                if Valid:
                    Chain.append(Block)
                    File_Name = Save_Block(Block)
                    print(f"[Received & Verified] {File_Name} | Hash: {Block['Hash'][:16]}...")
                else:
                    print(f"[Rejected] Block {Block['Index']} From {IP} | Reason: {Reason}")

        except Exception as E:
            print(f"[Error] Connection Lost To {IP} | {E}")
            break

def Scan_And_Connect():
    My_IP, Prefix = Get_Local_Info()
    Sockets = []
    Lock = threading.Lock()

    def Try_Connect(IP):
        try:
            S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            S.settimeout(0.2)
            S.connect((IP, Port))

            S.settimeout(2.0)

            Server_Greeting = S.recv(1024).decode()
            if Server_Greeting != "Mine_RX":
                S.close()
                return

            S.send("Mine_TX".encode())

            S.settimeout(None)

            with Lock:
                Sockets.append((IP, S))
                print(f"[Verified & Connected] {IP}")
        except:
            pass

    print("[Scanning] 15-Second Discovery Window...")
    Start_Time = time.time()

    while time.time() - Start_Time < 15:
        Threads = []
        for i in range(1, 255):
            IP = f"{Prefix}{i}"

            if IP == My_IP or IP == "127.0.0.1":
                continue

            T = threading.Thread(target=Try_Connect, args=(IP,))
            Threads.append(T)
            T.start()

        for T in Threads:
            T.join()

        if len(Sockets) > 0:
            break

        time.sleep(0.5)

    return Sockets

def Start_Client():
    Init_Folder()
    Chain = []

    while True:
        Connections = Scan_And_Connect()

        if len(Connections) >= 1:
            print(f"[Success] Established {len(Connections)} Verified Connection(s).")

            for IP, Sock in Connections:
                T = threading.Thread(target=Receive_Loop, args=(Sock, IP, Chain), daemon=True)
                T.start()

            for IP, Sock in Connections:
                pass

            while threading.active_count() > 1:
                time.sleep(1)

            break
        else:
            print("[Timeout] No Verified Servers Found. Sleeping 60 Seconds...")
            time.sleep(60)

Start_Client()