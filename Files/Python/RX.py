import socket
import os
import sys
import threading
import time
import json
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

Host     = "0.0.0.0"
Port     = 5000
Folder   = "Blocks"
BANNER_W = 60

Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"

Chain      = []
Chain_Lock = threading.Lock()

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
    return hashlib.sha256(Text.encode("utf-8")).hexdigest()

def SHA256_File(Path):
    with open(Path, "rb") as F:
        return hashlib.sha256(F.read()).hexdigest()

def Calculate_Hash(Block):
    Raw = f"{Block['Block']}{Block['Timestamp']}{json.dumps(Block['Data'], sort_keys=True)}{Block['Prev_Hash']}"
    return SHA256(Raw)

def Save_Block(Block):
    os.makedirs(Folder, exist_ok=True)
    Path = os.path.join(Folder, f"block_{Block['Block']}.json")
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return Path

def Recv_Length_Prefixed(Sock):
    Header = b""
    while len(Header) < 4:
        Chunk = Sock.recv(4 - len(Header))
        if not Chunk:
            return None
        Header += Chunk
    Length = int.from_bytes(Header, "big")
    Buf    = b""
    while len(Buf) < Length:
        Chunk = Sock.recv(min(65536, Length - len(Buf)))
        if not Chunk:
            return None
        Buf += Chunk
    return Buf

def Validate_Genesis(Block):
    if Block.get("Block") != 0:
        return False, "Genesis Index Must Be 0"
    if Block.get("Prev_Hash") not in ("", "0" * 64):
        return False, "Genesis Prev_Hash Must Be Empty Or 64 Zeros"
    return True, "Valid"

def Validate_Block(Block, Prev_Block):
    if Block["Block"] != Prev_Block["Block"] + 1:
        return False, f"Index Mismatch (Expected {Prev_Block['Block'] + 1}, Got {Block['Block']})"
    if Block["Prev_Hash"] != Prev_Block["Hash"]:
        return False, "Prev_Hash Mismatch"
    Recomputed = Calculate_Hash(Block)
    if Recomputed != Block["Hash"]:
        return False, "Hash Recompute Failed"
    return True, "Valid"

def Handle_TX(Client_Socket, Addr):
    global Chain

    print(f"\n  [Connected]   TX Node At {Addr[0]} Is Connecting...")

    try:
        Client_Socket.settimeout(5.0)
        Client_Socket.send(Handshake_A.encode())

        Response = Client_Socket.recv(1024).decode()
        if Response != Handshake_B:
            print(f"  [Auth Failed] Wrong Response From {Addr[0]}: '{Response}'")
            Client_Socket.close()
            return

        Client_Socket.settimeout(None)
        print(f"  [Auth OK]     {Addr[0]} Verified As TX Node ✓")

    except Exception as E:
        print(f"  [Auth Error]  Handshake Failed With {Addr[0]} | {E}")
        Client_Socket.close()
        return

    print(f"  [Listening]   Waiting For Blocks From {Addr[0]}...\n")

    while True:
        try:
            Raw = Recv_Length_Prefixed(Client_Socket)
            if Raw is None:
                print(f"\n  [Offline]   TX Node {Addr[0]} Closed Connection.")
                break

            Block = json.loads(Raw.decode("utf-8"))

            if not isinstance(Block, dict) or "Block" not in Block:
                print(f"  [Invalid]   Non-Block Packet From {Addr[0]}")
                continue

            with Chain_Lock:
                Local_Chain = list(Chain)

            if not Local_Chain:
                G_Ok, G_Reason = Validate_Genesis(Block)
                if G_Ok:
                    Path      = Save_Block(Block)
                    File_Hash = SHA256_File(Path)
                    print(f"  [Received]  Block 0 (Genesis) From {Addr[0]}")
                    print(f"  [Hash]      {Block['Hash']}")
                    print(f"  [File SHA]  {File_Hash[:40]}...")
                    with Chain_Lock:
                        Chain.append(Block)
                else:
                    print(f"  [Rejected]  Genesis Invalid | {G_Reason}")
            else:
                with Chain_Lock:
                    Prev = Chain[-1]
                V_Ok, V_Reason = Validate_Block(Block, Prev)
                if V_Ok:
                    Path      = Save_Block(Block)
                    File_Hash = SHA256_File(Path)
                    print(f"\n  [Received]  Block {Block['Block']} From {Addr[0]}")
                    print(f"  [Hash]      {Block['Hash']}")
                    print(f"  [Prev Hash] {Block['Prev_Hash'][:40]}...")
                    print(f"  [File SHA]  {File_Hash[:40]}...")
                    with Chain_Lock:
                        Chain.append(Block)
                else:
                    print(f"  [Rejected]  Block {Block['Block']} | {V_Reason}")

        except Exception as E:
            print(f"  [Error]     Lost Connection To {Addr[0]} | {E}")
            break

    Client_Socket.close()

def Accept_Loop(Server_Socket):
    while True:
        try:
            Client_Socket, Addr = Server_Socket.accept()
            Client_Socket.settimeout(None)
            Thread = threading.Thread(
                target=Handle_TX,
                args=(Client_Socket, Addr),
                daemon=True
            )
            Thread.start()
        except Exception as E:
            print(f"  [Accept Err] {E}")

def Start_RX():
    Node_IP = Get_Local_IP()

    Banner("FerroFy RX — Blockchain Receiver Node 🔗")
    print(f"  Node IP  :  {Node_IP}")
    print(f"  Port     :  {Port}")
    print(f"  Blocks   :  {Folder}/")
    print("=" * BANNER_W)
    print(f"\n  [Ready]    Listening For TX Connections On {Node_IP}:{Port}")
    print(f"  [Info]     Share This IP With TX Node To Start Receiving\n")
    print("=" * BANNER_W)

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(10)

    Accept_Thread = threading.Thread(
        target=Accept_Loop,
        args=(Server_Socket,),
        daemon=True
    )
    Accept_Thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  [Shutdown]  RX Node Stopped.")
        Server_Socket.close()

Start_RX()