import socket
import os
import sys
import threading
import time
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Chain_Verify import (
    Calculate_Hash, Verify_Full_Chain, Save_Block_To_File as Save_Block,
    Get_Missing_Indices, SHA256_Str, SHA256_File, Folder,
    Create_Genesis_Block, Create_New_Block
)

Host = "0.0.0.0"
Port = 5000
Folder = "Blocks"

Connected_Clients = []
Clients_Lock = threading.Lock()

def Banner(Text, Char="="):
    print(Char * BANNER_W)
    print(f"  {Text}")
    print(Char * BANNER_W)

def Get_Local_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        IP = S.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        S.close()
    return IP

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Load_Chain():
    Chain = []
    if not os.path.exists(Folder):
        return Chain
    Files = [F for F in os.listdir(Folder) if F.endswith(".json")]
    for File in Files:
        try:
            with open(os.path.join(Folder, File), "r") as F:
                Block = json.load(F)
                Chain.append(Block)
        except:
            pass
    Chain.sort(key=lambda B: B["Index"])
    return Chain

def Get_Last_Block(Chain):
    if not Chain:
        return None
    return Chain[-1]

def Build_Genesis_Block(Node_IP):
    Index = 0
    Timestamp = time.time()
    Data = {"Message": "Genesis Block", "Node": Node_IP}
    Previous_Hash = "0" * 64
    Hash = Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash)
    return {
        "Index": Index,
        "Timestamp": Timestamp,
        "Data": Data,
        "Previous_Hash": Previous_Hash,
        "Hash": Hash
    }

def Build_Next_Block(Previous_Block, Message, Node_IP):
    Index = Previous_Block["Index"] + 1
    Timestamp = time.time()
    Data = {
        "Message": Message,
        "Node": Node_IP,
        "Block_Time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(Timestamp))
    }
    Previous_Hash = Previous_Block["Hash"]
    Hash = Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash)
    return {
        "Index": Index,
        "Timestamp": Timestamp,
        "Data": Data,
        "Previous_Hash": Previous_Hash,
        "Hash": Hash
    }

def Save_Block(Block):
    File_Name = f"{Block['Index']}.json"
    Path = os.path.join(Folder, File_Name)
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return File_Name

def Send_Length_Prefixed(Sock, Payload_Bytes):
    Length = len(Payload_Bytes)
    Header = Length.to_bytes(4, byteorder="big")
    Sock.sendall(Header + Payload_Bytes)

def Broadcast_Block(Block):
    Payload = json.dumps(Block).encode()
    Dead = []
    with Clients_Lock:
        for Entry in Connected_Clients:
            IP, Sock = Entry
            try:
                Send_Length_Prefixed(Sock, Payload)
                print(f"[Broadcast] Block {Block['Index']} -> {IP}")
            except:
                print(f"[Dropped] Client {IP} Disconnected During Broadcast")
                Dead.append(Entry)
        for Entry in Dead:
            Connected_Clients.remove(Entry)

def Handle_Client(Client_Socket, Addr, Chain):
    print(f"\n[Connected] {Addr} - Verifying Handshake...")

    try:
        Client_Socket.settimeout(2.0)
        Client_Socket.send("Mine_RX".encode())

        Client_Response = Client_Socket.recv(1024).decode()

        if Client_Response != "Mine_TX":
            print(f"[Auth Failed] Wrong Password From {Addr}")
            Client_Socket.close()
            return

        Client_Socket.settimeout(None)
        print(f"[Auth Success] {Addr} Is Now A Verified Receiver")

    except:
        print(f"[Auth Failed] Handshake Dropped With {Addr}")
        Client_Socket.close()
        return

    with Clients_Lock:
        Connected_Clients.append((Addr[0], Client_Socket))

    try:
        for Block in Chain:
            Payload = json.dumps(Block).encode()
            Send_Length_Prefixed(Client_Socket, Payload)
            print(f"[Sync] Sent Existing Block {Block['Index']} -> {Addr[0]}")
            time.sleep(0.1)
    except:
        print(f"[Sync Failed] Could Not Send History To {Addr[0]}")

def Accept_Loop(Server_Socket, Chain):
    while True:
        try:
            Client_Socket, Addr = Server_Socket.accept()
            Client_Socket.settimeout(None)
            Thread = threading.Thread(
                target=Handle_Client,
                args=(Client_Socket, Addr, Chain),
                daemon=True
            )
            Thread.start()
        except:
            pass

def Start_Server():
    Init_Folder()
    Node_IP = Get_Local_IP()

    Chain = Load_Chain()

    if not Chain:
        Genesis = Build_Genesis_Block(Node_IP)
        Chain.append(Genesis)
        File_Name = Save_Block(Genesis)
        print(f"[Genesis] Created {File_Name} | Hash: {Genesis['Hash'][:16]}...")
    else:
        print(f"[Loaded] {len(Chain)} Existing Block(s) From '{Folder}/'")
        Last = Get_Last_Block(Chain)
        print(f"[Chain Tip] Block {Last['Index']} | Hash: {Last['Hash'][:16]}...")

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(100)

    print(f"[Server Running] IP: {Node_IP} | Port: {Port}")
    print(f"[Ready] Type A Message And Press Enter To Mine A New Block\n")

    Accept_Thread = threading.Thread(
        target=Accept_Loop,
        args=(Server_Socket, Chain),
        daemon=True
    )
    Accept_Thread.start()

    while True:
        try:
            Message = input("📝 Message > ").strip()
            if not Message:
                print("[Skipped] Empty Message. Please Type Something.")
                continue

            Last_Block = Get_Last_Block(Chain)
            New_Block = Build_Next_Block(Last_Block, Message, Node_IP)
            Chain.append(New_Block)

            File_Name = Save_Block(New_Block)
            print(f"[Mined] {File_Name} | Index: {New_Block['Index']} | Hash: {New_Block['Hash'][:16]}...")
            print(f"[Prev]  Chained To Block {Last_Block['Index']} | Hash: {Last_Block['Hash'][:16]}...")

            with Clients_Lock:
                Client_Count = len(Connected_Clients)

            if Client_Count > 0:
                Broadcast_Block(New_Block)
            else:
                print("[Info] No RX Clients Connected. Block Saved Locally.\n")

        except KeyboardInterrupt:
            print("\n[Shutdown] TX Node Stopped.")
            break

Start_TX()