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

Port      = 5000
Folder    = "Blocks"
BANNER_W  = 60

Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"

Chain       = []
RX_Sock     = None
RX_IP       = None

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

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Init_Folder():
    os.makedirs(Folder, exist_ok=True)

def Load_Chain():
    Chain_Data = []
    if not os.path.exists(Folder):
        return Chain_Data
    Files = [F for F in os.listdir(Folder) if F.endswith(".json")]
    for File in Files:
        try:
            with open(os.path.join(Folder, File), "r") as F:
                Block = json.load(F)
                Chain_Data.append(Block)
        except:
            pass
    Chain_Data.sort(key=lambda B: B["Block"])
    return Chain_Data

def Get_Last_Block(Chain_Data):
    if not Chain_Data:
        return None
    return Chain_Data[-1]

def Build_Genesis_Block(Node_IP):
    Index       = 0
    Timestamp   = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Data        = {"Message": "Genesis Block", "Node": Node_IP}
    Prev_Hash   = "0" * 64
    Hash        = Compute_Block_Hash(Index, Timestamp, Data, Prev_Hash)
    return {
        "Block":     Index,
        "Timestamp": Timestamp,
        "Data":      Data,
        "Prev_Hash": Prev_Hash,
        "Hash":      Hash
    }

def Build_Next_Block(Previous_Block, Message, Node_IP):
    Index     = Previous_Block["Block"] + 1
    Timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Data      = {
        "Message":    Message,
        "Node":       Node_IP,
        "Block_Time": Timestamp
    }
    Prev_Hash = Previous_Block["Hash"]
    Hash      = Compute_Block_Hash(Index, Timestamp, Data, Prev_Hash)
    return {
        "Block":     Index,
        "Timestamp": Timestamp,
        "Data":      Data,
        "Prev_Hash": Prev_Hash,
        "Hash":      Hash
    }

def Save_Block(Block):
    File_Name = f"block_{Block['Block']}.json"
    Path      = os.path.join(Folder, File_Name)
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return File_Name

def Send_Length_Prefixed(Sock, Payload_Bytes):
    Length = len(Payload_Bytes)
    Header = Length.to_bytes(4, byteorder="big")
    Sock.sendall(Header + Payload_Bytes)

def Send_Block(Sock, Block):
    Payload = json.dumps(Block).encode("utf-8")
    Send_Length_Prefixed(Sock, Payload)

def Connect_To_RX(Target_IP):
    global RX_Sock, RX_IP
    print(f"\n  [Connecting]  Attempting {Target_IP}:{Port}...")
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5.0)
        S.connect((Target_IP, Port))

        Greeting = S.recv(1024).decode()
        if Greeting != Handshake_A:
            print(f"  [Auth Failed] Unexpected Handshake: '{Greeting}'")
            S.close()
            return False

        S.send(Handshake_B.encode())
        S.settimeout(None)

        RX_Sock = S
        RX_IP   = Target_IP
        print(f"  [Connected]   Verified With {Target_IP} ✓")
        return True

    except Exception as E:
        print(f"  [Failed]      Could Not Connect To {Target_IP} | {E}")
        return False

def Start_TX():
    global Chain, RX_Sock, RX_IP

    Init_Folder()
    Node_IP = Get_Local_IP()

    Banner("FerroFy TX — Blockchain Transmitter Node 📡")
    print(f"  Node IP  :  {Node_IP}")
    print(f"  Port     :  {Port}")
    print(f"  Blocks   :  {Folder}/")
    print("=" * BANNER_W)

    while True:
        Target = input("\n🔗 Enter RX Node IP To Connect > ").strip()
        if not Target:
            print("  [Error]  IP Cannot Be Empty.")
            continue
        if Connect_To_RX(Target):
            break
        Retry = input("  [Retry?]  Try Another IP? (y/n) > ").strip().lower()
        if Retry != "y":
            print("  [Exiting]  No Connection Established.")
            return

    Chain = Load_Chain()

    if not Chain:
        Genesis   = Build_Genesis_Block(Node_IP)
        Chain.append(Genesis)
        File_Name = Save_Block(Genesis)
        print(f"\n  [Genesis]  Created {File_Name} | Hash: {Genesis['Hash'][:16]}...")
        try:
            Send_Block(RX_Sock, Genesis)
            print(f"  [Sent]     Genesis Block -> {RX_IP}")
        except Exception as E:
            print(f"  [Send Err] Could Not Send Genesis | {E}")
    else:
        print(f"\n  [Loaded]   {len(Chain)} Existing Block(s) From '{Folder}/'")
        Last = Get_Last_Block(Chain)
        print(f"  [Tip]      Block {Last['Block']} | Hash: {Last['Hash'][:16]}...")
        print(f"\n  [Sync]     Sending {len(Chain)} Existing Block(s) To {RX_IP}...")
        for Block in Chain:
            try:
                Send_Block(RX_Sock, Block)
                print(f"  [Sent]     Block {Block['Block']} -> {RX_IP}")
                time.sleep(0.05)
            except Exception as E:
                print(f"  [Err]      Block {Block['Block']} Failed | {E}")
                break

    print(f"\n  [Ready]    Type A Message To Mine And Transmit A Block\n")
    print("=" * BANNER_W)

    while True:
        try:
            Message = input("\n📝 Message > ").strip()
            if not Message:
                print("  [Skipped]  Empty Message.")
                continue

            Last_Block = Get_Last_Block(Chain)
            New_Block  = Build_Next_Block(Last_Block, Message, Node_IP)
            Chain.append(New_Block)

            File_Name = Save_Block(New_Block)
            print(f"  [Mined]    {File_Name} | Block: {New_Block['Block']} | Hash: {New_Block['Hash'][:16]}...")
            print(f"  [Chained]  Block {Last_Block['Block']} | Hash: {Last_Block['Hash'][:16]}...")

            if RX_Sock:
                try:
                    Send_Block(RX_Sock, New_Block)
                    print(f"  [Sent]     Block {New_Block['Block']} -> {RX_IP}")
                except Exception as E:
                    print(f"  [Err]      Failed To Send Block {New_Block['Block']} | {E}")
                    RX_Sock = None
            else:
                print("  [Info]     Not Connected To Any RX. Block Saved Locally.")

        except KeyboardInterrupt:
            print("\n\n  [Shutdown] TX Node Stopped.")
            if RX_Sock:
                RX_Sock.close()
            break

Start_TX()