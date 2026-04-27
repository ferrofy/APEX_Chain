import socket
import os
import threading
import time
import json
import hashlib

Host = "0.0.0.0"
Port = 5000
Folder = "Blocks"
Block_Interval = 60

def Init_Folder():
    if not os.path.exists(Folder):
        os.makedirs(Folder)

def Get_Local_IP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        IP = s.getsockname()[0]
    except:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Build_Genesis_Block():
    Index = 0
    Timestamp = time.time()
    Data = {"Message": "Genesis Block", "Node": Get_Local_IP()}
    Previous_Hash = "0" * 64
    Hash = Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash)
    return {
        "Index": Index,
        "Timestamp": Timestamp,
        "Data": Data,
        "Previous_Hash": Previous_Hash,
        "Hash": Hash
    }

def Build_Next_Block(Previous_Block, Node_IP):
    Index = Previous_Block["Index"] + 1
    Timestamp = time.time()
    Data = {
        "Message": f"Block {Index} From {Node_IP}",
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

def Handle_Client(Client_Socket, Addr, Chain):
    print(f"[CONNECTED] {Addr} - Verifying...")

    try:
        Client_Socket.settimeout(2.0)
        Client_Socket.send("Mine_RX".encode())

        Client_Response = Client_Socket.recv(1024).decode()

        if Client_Response != "Mine_TX":
            print(f"[Auth Failed] Incorrect Password From {Addr}")
            Client_Socket.close()
            return

        Client_Socket.settimeout(None)
        print(f"[Auth Success] Handshake Complete With {Addr}")

    except:
        print(f"[Auth Failed] Connection Dropped During Handshake With {Addr}")
        Client_Socket.close()
        return

    Node_IP = Addr[0]

    while True:
        try:
            Previous_Block = Chain[-1]
            New_Block = Build_Next_Block(Previous_Block, Node_IP)
            Chain.append(New_Block)

            File_Name = Save_Block(New_Block)
            print(f"[Mined] {File_Name} | Hash: {New_Block['Hash'][:16]}...")

            Payload = json.dumps(New_Block).encode()
            Send_Length_Prefixed(Client_Socket, Payload)
            print(f"[Sent] {File_Name} -> {Addr}")

            print(f"[Waiting] Next Block In {Block_Interval} Seconds...")
            time.sleep(Block_Interval)

        except Exception as E:
            print(f"[Disconnected] {Addr} | {E}")
            Client_Socket.close()
            break

def Start_Server():
    Init_Folder()

    Chain = [Build_Genesis_Block()]
    Save_Block(Chain[0])
    print(f"[Genesis] Block 0 Created | Hash: {Chain[0]['Hash'][:16]}...")

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(100)
    Server_Socket.settimeout(10.0)

    print(f"[Server Running] IP: {Get_Local_IP()} | Port: {Port}")

    while True:
        try:
            print("[Listening] Waiting For New Connections...")
            Client_Socket, Addr = Server_Socket.accept()
            Client_Socket.settimeout(None)
            Thread = threading.Thread(target=Handle_Client, args=(Client_Socket, Addr, Chain), daemon=True)
            Thread.start()

        except socket.timeout:
            print("[Timeout] No New Connections. Continuing...")

Start_Server()