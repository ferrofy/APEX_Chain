import socket
import os
import sys
import threading
import time
import json
import collections

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Chain_Verify import (
    Compute_Block_Hash, Verify_Full_Chain, Save_Block,
    Get_Missing_Indices, SHA256_Str, SHA256_File, Folder,
    Load_All_Blocks
)

Port        = 5000
Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"
BANNER_W    = 60

Chain      = []
Chain_Lock = threading.Lock()

def Banner(Text, Char="="):
    print(Char * BANNER_W)
    print(f"  {Text}")
    print(Char * BANNER_W)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        IP = S.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        S.close()
    Prefix = ".".join(IP.split(".")[:-1]) + "."
    return IP, Prefix

def Send_LP(Sock, Data_Bytes):
    Sock.sendall(len(Data_Bytes).to_bytes(4, "big") + Data_Bytes)

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

def Validate_Block(Block, Prev_Block):
    if Block["Index"] != Prev_Block["Index"] + 1:
        return False, f"Index Mismatch (Expected {Prev_Block['Index']+1}, Got {Block['Index']})"
    if Block["Previous_Hash"] != Prev_Block["Hash"]:
        return False, "Previous_Hash Mismatch"
    Recomputed = Compute_Block_Hash(
        Block["Index"], Block["Timestamp"], Block["Data"], Block["Previous_Hash"]
    )
    if Recomputed != Block["Hash"]:
        return False, "Hash Recompute Failed"
    return True, "Valid"

def Validate_Genesis(Block):
    if Block["Index"] != 0:
        return False, "Genesis Index Must Be 0"
    if Block["Previous_Hash"] != "0" * 64:
        return False, "Genesis Previous_Hash Must Be 64 Zeros"
    Recomputed = Compute_Block_Hash(
        Block["Index"], Block["Timestamp"], Block["Data"], Block["Previous_Hash"]
    )
    if Recomputed != Block["Hash"]:
        return False, "Genesis Hash Recompute Failed"
    return True, "Valid"

def Scan_Network(My_IP, Prefix, N_Threads=254):
    Found = []
    Lock  = threading.Lock()

    def Try(IP):
        try:
            S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            S.settimeout(0.35)
            S.connect((IP, Port))
            S.settimeout(3.0)
            Greeting = S.recv(1024).decode()
            if Greeting != Handshake_A:
                S.close()
                return
            S.send(Handshake_B.encode())
            S.settimeout(None)
            with Lock:
                Found.append((IP, S))
                print(f"  [Peer Found]  Connected & Verified → {IP}")
        except Exception:
            pass

    Threads = []
    for i in range(1, 255):
        IP = f"{Prefix}{i}"
        if IP in (My_IP, "127.0.0.1"):
            continue
        T = threading.Thread(target=Try, args=(IP,), daemon=True)
        Threads.append(T)
        T.start()

    for T in Threads:
        T.join()

    return Found

def Request_Block_From_Peer(Sock, Index):
    try:
        Send_Msg(Sock, {"Type": "REQUEST_BLOCK", "Index": Index})
        Sock.settimeout(5.0)
        Reply = Recv_Msg(Sock)
        Sock.settimeout(None)
        if Reply and Reply.get("Type") == "BLOCK_REPLY":
            return Reply.get("Block")
    except Exception:
        pass
    return None

def Majority_Block(Responses):
    Valid_Blocks = [B for B in Responses if B is not None]
    if not Valid_Blocks:
        return None
    Counter  = collections.Counter(json.dumps(B, sort_keys=True) for B in Valid_Blocks)
    Top_Json, Top_Count = Counter.most_common(1)[0]
    N_Peers  = len(Responses)
    Threshold = N_Peers // 2 + 1 if N_Peers > 1 else 1
    if Top_Count >= Threshold:
        return json.loads(Top_Json)
    return None

def Collect_Chain_From_Peers(Peers):
    if not Peers:
        return []

    N = len(Peers)
    print(f"\n  [Recovery]  Requesting Chain Data From {N} Peer(s)...\n")

    All_Blocks_By_Index = collections.defaultdict(list)

    def Drain_Peer(IP, Sock, Received):
        try:
            while True:
                Sock.settimeout(4.0)
                Raw = Recv_LP(Sock)
                if Raw is None:
                    break
                Block = json.loads(Raw.decode("utf-8"))
                if isinstance(Block, dict) and "Index" in Block:
                    Received.append(Block)
        except Exception:
            pass

    Thread_Results = {}
    Drain_Threads  = []

    for IP, Sock in Peers:
        Thread_Results[IP] = []
        T = threading.Thread(
            target=Drain_Peer,
            args=(IP, Sock, Thread_Results[IP]),
            daemon=True
        )
        Drain_Threads.append((IP, T))
        T.start()

    for _, T in Drain_Threads:
        T.join(timeout=8)

    for IP, Blocks in Thread_Results.items():
        print(f"  [Peer {IP}]  Received {len(Blocks)} Block(s)")
        for B in Blocks:
            All_Blocks_By_Index[B["Index"]].append(B)

    if not All_Blocks_By_Index:
        return []

    Max_Index = max(All_Blocks_By_Index.keys())
    print(f"\n  [Consensus] Running Block-By-Block Majority Vote (0 → {Max_Index})...\n")

    Agreed_Chain = []

    for Idx in range(0, Max_Index + 1):
        Candidates = All_Blocks_By_Index.get(Idx, [])
        Padding    = [None] * (N - len(Candidates))
        Responses  = Candidates + Padding
        Winner     = Majority_Block(Responses)

        if Winner is None:
            Count = len(Candidates)
            print(f"  Block {Idx:>4} | No Majority ({Count}/{N} Responded) — Skipped")
            break

        if Idx == 0:
            G_Ok, G_Reason = Validate_Genesis(Winner)
            Status = "OK" if G_Ok else f"INVALID ({G_Reason})"
            print(f"  Block {Idx:>4} | Hash: {Winner['Hash'][:16]}... | Genesis: {Status}")
            if not G_Ok:
                break
            Agreed_Chain.append(Winner)
        else:
            if not Agreed_Chain:
                break
            V_Ok, V_Reason = Validate_Block(Winner, Agreed_Chain[-1])
            Status = "OK" if V_Ok else f"INVALID ({V_Reason})"
            print(f"  Block {Idx:>4} | Hash: {Winner['Hash'][:16]}... | Chain Link: {Status}")
            if not V_Ok:
                break
            Agreed_Chain.append(Winner)

    return Agreed_Chain

def Apply_Agreed_Chain(Agreed_Chain):
    os.makedirs(Folder, exist_ok=True)
    for Block in Agreed_Chain:
        Path = Save_Block(Block)
        print(f"  [Saved]  Block {Block['Index']} → {os.path.basename(Path)}")

def Receive_New_Blocks(Sock, IP):
    global Chain
    print(f"  [Listening] Waiting For New Blocks From {IP}...")
    while True:
        try:
            Raw = Recv_LP(Sock)
            if Raw is None:
                print(f"  [Offline]   Server {IP} Closed Connection")
                break

            Block = json.loads(Raw.decode("utf-8"))

            if isinstance(Block, dict) and Block.get("Type") == "BLOCK_REPLY":
                continue

            with Chain_Lock:
                Local_Chain = list(Chain)

            if not Local_Chain:
                G_Ok, G_Reason = Validate_Genesis(Block)
                if G_Ok:
                    Path = Save_Block(Block)
                    File_Hash = SHA256_File(Path)
                    print(f"\n  [Received]  Block 0 (Genesis)")
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
                    Path = Save_Block(Block)
                    File_Hash = SHA256_File(Path)
                    print(f"\n  [Received]  Block {Block['Index']}")
                    print(f"  [Hash]      {Block['Hash']}")
                    print(f"  [Prev Hash] {Block['Previous_Hash'][:40]}...")
                    print(f"  [File SHA]  {File_Hash[:40]}...")
                    with Chain_Lock:
                        Chain.append(Block)
                else:
                    print(f"  [Rejected]  Block {Block['Index']} From {IP} | {V_Reason}")

        except Exception as E:
            print(f"  [Error]     Lost Connection To {IP} | {E}")
            break

def Start_RX():
    global Chain

    My_IP, Prefix = Get_Local_Info()

    Banner("FerroFy RX — Peer Blockchain Node 🔗")
    print(f"  Node IP  :  {My_IP}")
    print(f"  Port     :  {Port}")
    print(f"  Blocks   :  {Folder}")
    print("=" * BANNER_W)

    print("\n  [Local Chain] Verifying Local Blocks First...\n")
    Local_Chain, Corrupt = Verify_Full_Chain(Verbose=True)

    print("\n  [Scan] Discovering Peers On LAN...\n")
    Peers = Scan_Network(My_IP, Prefix)

    N = len(Peers)
    print(f"\n  [Peers]   {N} Active Peer(s) Found")

    if N == 0:
        print("  [Waiting] No Peers Found. Retrying In 60 Seconds...")
        time.sleep(60)
        Start_RX()
        return

    print(f"\n  [Analysis] Local Blocks: {len(Local_Chain)} | Corrupt: {len(Corrupt)}")

    Needs_Recovery = len(Corrupt) > 0 or len(Local_Chain) == 0

    if Needs_Recovery:
        print(f"\n  [Recovery] Chain Is Incomplete Or Corrupt. Starting Peer Correction...\n")
        Agreed_Chain = Collect_Chain_From_Peers(Peers)
        if Agreed_Chain:
            print(f"\n  [Applying] Writing {len(Agreed_Chain)} Consensus Block(s) To Disk...\n")
            Apply_Agreed_Chain(Agreed_Chain)
            with Chain_Lock:
                Chain = Agreed_Chain
            print(f"\n  [OK]       Chain Restored To {len(Chain)} Block(s) Via {N}-Node Majority.\n")
        else:
            print("  [Fail]     Could Not Reach Majority. Chain Left As-Is.\n")
            with Chain_Lock:
                Chain = Local_Chain
    else:
        print("  [OK]       Local Chain Is Clean. Skipping Recovery.\n")
        with Chain_Lock:
            Chain = Local_Chain

    print("=" * BANNER_W)
    print(f"  [Ready]    Listening For New Blocks From {N} Peer(s)...\n")

    Recv_Threads = []
    for IP, Sock in Peers:
        T = threading.Thread(
            target=Receive_New_Blocks,
            args=(Sock, IP),
            daemon=True
        )
        T.start()
        Recv_Threads.append(T)

    try:
        while any(T.is_alive() for T in Recv_Threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n  [Shutdown]  RX Node Stopping.")

Start_RX()