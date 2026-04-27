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
    Compute_Block_Hash, Verify_Full_Chain, Save_Block,
    Get_Missing_Indices, SHA256_Str, SHA256_File, Folder
)

Host        = "0.0.0.0"
Port        = 5000
Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"
BANNER_W    = 60

Connected_Peers = []
Peers_Lock      = threading.Lock()
Chain_Lock      = threading.Lock()

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

def Build_Genesis_Block(Node_IP):
    Index         = 0
    Timestamp     = time.time()
    Data          = {"Message": "Genesis Block", "Node": Node_IP}
    Previous_Hash = "0" * 64
    Hash          = Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash)
    return {
        "Index":         Index,
        "Timestamp":     Timestamp,
        "Data":          Data,
        "Previous_Hash": Previous_Hash,
        "Hash":          Hash
    }

def Build_Next_Block(Prev_Block, Message, Node_IP):
    Index         = Prev_Block["Index"] + 1
    Timestamp     = time.time()
    Data          = {
        "Message":    Message,
        "Node":       Node_IP,
        "Block_Time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(Timestamp))
    }
    Previous_Hash = Prev_Block["Hash"]
    Hash          = Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash)
    return {
        "Index":         Index,
        "Timestamp":     Timestamp,
        "Data":          Data,
        "Previous_Hash": Previous_Hash,
        "Hash":          Hash
    }

def Send_LP(Sock, Data_Bytes):
    Length = len(Data_Bytes)
    Sock.sendall(Length.to_bytes(4, "big") + Data_Bytes)

def Recv_LP(Sock):
    Header = b""
    while len(Header) < 4:
        Chunk = Sock.recv(4 - len(Header))
        if not Chunk:
            return None
        Header += Chunk
    Length = int.from_bytes(Header, "big")
    Buf = b""
    while len(Buf) < Length:
        Chunk = Sock.recv(min(65536, Length - len(Buf)))
        if not Chunk:
            return None
        Buf += Chunk
    return Buf

def Send_Msg(Sock, Obj):
    Send_LP(Sock, json.dumps(Obj).encode("utf-8"))

def Recv_Msg(Sock):
    Raw = Recv_LP(Sock)
    if Raw is None:
        return None
    return json.loads(Raw.decode("utf-8"))

def Broadcast_Block(Block):
    Payload = json.dumps(Block).encode("utf-8")
    Dead    = []
    with Peers_Lock:
        for (IP, Sock) in Connected_Peers:
            try:
                Send_LP(Sock, Payload)
                print(f"  [Broadcast] Block {Block['Index']} ──► {IP}")
            except Exception:
                print(f"  [Dropped]   Peer {IP} Disconnected During Broadcast")
                Dead.append((IP, Sock))
        for Entry in Dead:
            Connected_Peers.remove(Entry)

def Handle_Peer(Client_Sock, Addr, Chain):
    IP = Addr[0]
    print(f"\n  [Incoming]  Connection From {IP} — Verifying Handshake...")
    try:
        Client_Sock.settimeout(3.0)
        Client_Sock.send(Handshake_A.encode())
        Response = Client_Sock.recv(1024).decode()
        if Response != Handshake_B:
            print(f"  [Auth Fail] Wrong Token From {IP}")
            Client_Sock.close()
            return
        Client_Sock.settimeout(None)
        print(f"  [Auth OK]   {IP} Is A Verified Peer")
    except Exception:
        print(f"  [Auth Fail] Handshake Dropped With {IP}")
        Client_Sock.close()
        return

    with Peers_Lock:
        Connected_Peers.append((IP, Client_Sock))

    with Chain_Lock:
        Snapshot = list(Chain)

    try:
        for Block in Snapshot:
            Payload = json.dumps(Block).encode("utf-8")
            Send_LP(Client_Sock, Payload)
            print(f"  [Sync]      Sent Existing Block {Block['Index']} ──► {IP}")
            time.sleep(0.05)
    except Exception:
        print(f"  [Sync Fail] Could Not Send History To {IP}")

    while True:
        try:
            Msg = Recv_Msg(Client_Sock)
            if Msg is None:
                break
            if Msg.get("Type") == "REQUEST_BLOCK":
                Idx = Msg.get("Index")
                with Chain_Lock:
                    Match = [B for B in Chain if B["Index"] == Idx]
                if Match:
                    Send_Msg(Client_Sock, {"Type": "BLOCK_REPLY", "Block": Match[0]})
                else:
                    Send_Msg(Client_Sock, {"Type": "BLOCK_REPLY", "Block": None})
        except Exception:
            break

    with Peers_Lock:
        Connected_Peers[:] = [(I, S) for (I, S) in Connected_Peers if I != IP]
    print(f"  [Offline]   Peer {IP} Disconnected")

def Accept_Loop(Server_Sock, Chain):
    while True:
        try:
            Client_Sock, Addr = Server_Sock.accept()
            Client_Sock.settimeout(None)
            T = threading.Thread(
                target=Handle_Peer,
                args=(Client_Sock, Addr, Chain),
                daemon=True
            )
            T.start()
        except Exception:
            pass

def Pre_Mine_Verify(Chain):
    Banner("Pre-Mine Chain Verification", "-")
    _, Corrupt = Verify_Full_Chain(Verbose=True)
    if Corrupt:
        print(f"\n  [Warning]   {len(Corrupt)} Corrupt Block(s). Recommend Peer Correction.")
    else:
        print(f"\n  [OK]        Chain Integrity Confirmed Before Mining.")
    print("-" * BANNER_W)
    return len(Corrupt) == 0

def Start_TX():
    os.makedirs(Folder, exist_ok=True)
    Node_IP = Get_Local_IP()

    Banner("FerroFy TX — Origin Blockchain Node 🔗")
    print(f"  Node IP  :  {Node_IP}")
    print(f"  Port     :  {Port}")
    print(f"  Blocks   :  {Folder}")
    print("=" * BANNER_W)

    Chain, Corrupt = Verify_Full_Chain(Verbose=True)

    if not Chain:
        print("\n  [Genesis]   No Chain Found. Creating Genesis Block...")
        Genesis = Build_Genesis_Block(Node_IP)
        Chain   = [Genesis]
        Path    = Save_Block(Genesis)
        print(f"  [Genesis]   Saved: {os.path.basename(Path)}")
        print(f"  [Genesis]   Hash:  {Genesis['Hash']}")
    else:
        Last = Chain[-1]
        print(f"\n  [Loaded]    {len(Chain)} Block(s) | Tip → Block {Last['Index']} | Hash: {Last['Hash'][:20]}...")
        if Corrupt:
            print(f"  [Warning]   {len(Corrupt)} Corrupt Block(s) Detected At: {Corrupt}")
            print(f"  [Info]      Connect RX Peers To Trigger Majority Correction.")

    print("=" * BANNER_W)

    Server_Sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Server_Sock.bind((Host, Port))
    Server_Sock.listen(100)

    print(f"  [Listening] Ready. Accepting Peer Connections On Port {Port}...")
    print(f"  [Mine]      Type A Message And Press Enter To Mine A New Block")
    print("=" * BANNER_W + "\n")

    Accept_T = threading.Thread(target=Accept_Loop, args=(Server_Sock, Chain), daemon=True)
    Accept_T.start()

    while True:
        try:
            Message = input("  ✏  Message > ").strip()
            if not Message:
                print("  [Skip]      Empty Message. Type Something.\n")
                continue

            Chain_OK = Pre_Mine_Verify(Chain)

            if not Chain_OK:
                print("  [Blocked]   Chain Has Corruption. Resolve Before Mining.\n")
                continue

            with Chain_Lock:
                Last_Block = Chain[-1]
                New_Block  = Build_Next_Block(Last_Block, Message, Node_IP)
                Chain.append(New_Block)

            Path = Save_Block(New_Block)
            File_Hash = SHA256_File(Path)

            print(f"\n  [Mined]     Block {New_Block['Index']}")
            print(f"  [Index]     {New_Block['Index']}")
            print(f"  [Hash]      {New_Block['Hash']}")
            print(f"  [Prev Hash] {New_Block['Previous_Hash'][:40]}...")
            print(f"  [File SHA]  {File_Hash[:40]}...")
            print(f"  [Saved]     {os.path.basename(Path)}\n")

            with Peers_Lock:
                N_Peers = len(Connected_Peers)

            if N_Peers > 0:
                Broadcast_Block(New_Block)
                print(f"  [Broadcast] Sent To {N_Peers} Peer(s)\n")
            else:
                print("  [Local]     No Peers Connected. Block Saved Locally.\n")

        except KeyboardInterrupt:
            print("\n\n  [Shutdown]  TX Node Stopping.")
            Server_Sock.close()
            break

Start_TX()