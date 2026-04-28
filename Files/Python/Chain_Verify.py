import hashlib
import json
import os
import sys
import time
import socket
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BLOCKS_DIR   = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Blocks")
SYNC_PORT    = 5003
SCAN_TIMEOUT = 0.4
SCAN_WORKERS = 60

def SHA256_Str(Text):
    return hashlib.sha256(Text.encode("utf-8")).hexdigest()

def SHA256_File(Path):
    with open(Path, "rb") as F:
        return hashlib.sha256(F.read()).hexdigest()

def Calculate_Hash(Block_Data):
    Core = {
        "Block":     Block_Data["Block"],
        "Timestamp": Block_Data["Timestamp"],
        "Data":      Block_Data["Data"],
        "Prev_Hash": Block_Data["Prev_Hash"],
    }
    return SHA256_Str(json.dumps(Core, sort_keys=True))

def Unix_Now():
    return int(time.time())

def Load_All_Blocks(Folder=None):
    Target = Folder or BLOCKS_DIR
    Chain  = []
    if not os.path.exists(Target):
        return Chain
    Files = sorted(
        [F for F in os.listdir(Target) if F.startswith("block_") and F.endswith(".json")],
        key=lambda F: int(F.replace("block_", "").replace(".json", ""))
    )
    for File in Files:
        Path = os.path.join(Target, File)
        try:
            with open(Path, "r") as F:
                Block = json.load(F)
                Chain.append((Block, Path))
        except Exception as E:
            print(f"  [Corrupt] Cannot Read {File} | {E}")
    return Chain

def Verify_Block_Hash(Block):
    if Block["Block"] == 0:
        Valid = Block["Hash"] == "0" * 64
        return Valid, Block["Hash"]
    Recomputed = Calculate_Hash(Block)
    return Recomputed == Block["Hash"], Recomputed

def Verify_Full_Chain(Folder=None, Verbose=True):
    Entries = Load_All_Blocks(Folder)
    Corrupt = []

    if not Entries:
        if Verbose:
            print("  [Chain] No Blocks Found.")
        return [], []

    if Verbose:
        print(f"\n  [Verify] Checking {len(Entries)} Block(s) From Genesis To Tip...\n")

    for i, (Block, Path) in enumerate(Entries):
        File      = os.path.basename(Path)
        File_Hash = SHA256_File(Path)

        Hash_Valid, _ = Verify_Block_Hash(Block)

        if i == 0:
            Chain_Link_Valid = Block["Prev_Hash"] == "" or Block["Prev_Hash"] == "0" * 64
        else:
            Prev_Block       = Entries[i - 1][0]
            Chain_Link_Valid = Block["Prev_Hash"] == Prev_Block["Hash"]

        Index_Valid = Block["Block"] == i
        All_Ok      = Hash_Valid and Chain_Link_Valid and Index_Valid

        if Verbose:
            Status = "OK" if All_Ok else "FAIL"
            print(f"  Block {Block['Block']:>4} | {File:<12} | File-SHA256: {File_Hash[:12]}... | Hash: {'OK' if Hash_Valid else 'FAIL'} | Link: {'OK' if Chain_Link_Valid else 'FAIL'} | [{Status}]")

        if not All_Ok:
            Corrupt.append(Block["Block"])

    if Verbose:
        if Corrupt:
            print(f"\n  [Chain] {len(Corrupt)} Corrupt Block(s) Detected At Index(es): {Corrupt}")
        else:
            print(f"\n  [Chain] All {len(Entries)} Block(s) Verified OK [PASS]")

    return [B for B, _ in Entries], Corrupt

def Get_Missing_Indices(Chain):
    if not Chain:
        return []
    Max_Index = Chain[-1]["Block"]
    Existing  = {B["Block"] for B in Chain}
    return [i for i in range(0, Max_Index + 1) if i not in Existing]

def Save_Block_To_File(Block, Folder_Override=None):
    Target = Folder_Override or BLOCKS_DIR
    os.makedirs(Target, exist_ok=True)
    Path = os.path.join(Target, f"block_{Block['Block']}.json")
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return Path

def Get_Local_Subnet():
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

def Probe_Peer(IP, Found, Lock):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(SCAN_TIMEOUT)
        S.connect((IP, SYNC_PORT))
        S.sendall(b"PING")
        S.settimeout(1.0)
        Reply = S.recv(16)
        S.close()
        if Reply == b"PONG":
            with Lock:
                Found.append(IP)
    except Exception:
        pass

def Discover_Peers(My_IP=None):
    Local_IP, Prefix = Get_Local_Subnet()
    Check_IP = My_IP or Local_IP

    Found   = []
    Lock    = threading.Lock()
    Threads = []

    for i in range(1, 255):
        IP = f"{Prefix}{i}"
        if IP == Check_IP:
            continue
        T = threading.Thread(target=Probe_Peer, args=(IP, Found, Lock), daemon=True)
        Threads.append(T)

    Batch = SCAN_WORKERS
    for k in range(0, len(Threads), Batch):
        Slice = Threads[k : k + Batch]
        for T in Slice:
            T.start()
        for T in Slice:
            T.join()

    return Found

def Fetch_Block_From_Peer(Peer_IP, Block_Index):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5)
        S.connect((Peer_IP, SYNC_PORT))
        Request = json.dumps({"Cmd": "GET_BLOCK", "Index": Block_Index}).encode("utf-8")
        S.sendall(Request)
        S.shutdown(socket.SHUT_WR)

        Raw = b""
        while True:
            Chunk = S.recv(8192)
            if not Chunk:
                break
            Raw += Chunk
        S.close()

        if not Raw or Raw == b"NOT_FOUND":
            return None
        return json.loads(Raw.decode("utf-8"))

    except Exception:
        return None

def Fetch_Chain_Length_From_Peer(Peer_IP):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5)
        S.connect((Peer_IP, SYNC_PORT))
        Request = json.dumps({"Cmd": "CHAIN_LEN"}).encode("utf-8")
        S.sendall(Request)
        S.shutdown(socket.SHUT_WR)

        Raw = b""
        while True:
            Chunk = S.recv(1024)
            if not Chunk:
                break
            Raw += Chunk
        S.close()

        return json.loads(Raw.decode("utf-8")).get("Length", 0)

    except Exception:
        return 0

def Majority_Vote_Block(Peers, Block_Index):
    Votes  = {}
    Blocks = {}

    for Peer in Peers:
        Block = Fetch_Block_From_Peer(Peer, Block_Index)
        if Block is None:
            continue
        Key = Block.get("Hash", "")
        Votes[Key]  = Votes.get(Key, 0) + 1
        Blocks[Key] = Block

    if not Votes:
        return None

    Best_Hash  = max(Votes, key=lambda K: Votes[K])
    Total      = len(Peers)
    Pct        = Votes[Best_Hash] / Total if Total > 0 else 0

    if Pct >= 0.51:
        return Blocks[Best_Hash]
    return None

def Repair_Chain(Corrupt_Indices, Peers, Verbose=True):
    if not Peers:
        if Verbose:
            print("  [Repair] No Peers Available. Cannot Repair.")
        return 0

    Repaired = 0
    for Index in Corrupt_Indices:
        if Verbose:
            print(f"  [Repair] Block #{Index} — Requesting From {len(Peers)} Peer(s)...")

        Winner = Majority_Vote_Block(Peers, Index)

        if Winner:
            Hash_OK, _ = Verify_Block_Hash(Winner)
            if Hash_OK:
                Save_Block_To_File(Winner)
                Repaired += 1
                if Verbose:
                    print(f"  [Repair] Block #{Index} Replaced  ✓  (51%+ Consensus)")
            else:
                if Verbose:
                    print(f"  [Repair] Block #{Index} Peer Data Invalid — Skipped")
        else:
            if Verbose:
                print(f"  [Repair] Block #{Index} No 51% Consensus — Cannot Repair")

    return Repaired

def Run_Verify_And_Repair(Verbose=True):
    Chain, Corrupt = Verify_Full_Chain(Verbose=Verbose)

    if not Corrupt:
        return Chain, []

    if Verbose:
        print(f"\n  [Sync] Scanning For Peer Data Nodes On Port {SYNC_PORT}...")

    Peers = Discover_Peers()

    if Verbose:
        print(f"  [Sync] Found {len(Peers)} Peer(s): {Peers}")

    Repaired = Repair_Chain(Corrupt, Peers, Verbose=Verbose)

    if Verbose and Repaired:
        print(f"\n  [Sync] {Repaired}/{len(Corrupt)} Block(s) Repaired. Re-Verifying...")
        Chain, Corrupt = Verify_Full_Chain(Verbose=Verbose)

    return Chain, Corrupt

def Handle_Sync_Request(Conn):
    try:
        Raw = b""
        Conn.settimeout(3)
        try:
            while True:
                Chunk = Conn.recv(8192)
                if not Chunk:
                    break
                Raw += Chunk
        except socket.timeout:
            pass

        if Raw == b"PING":
            Conn.sendall(b"PONG")
            return

        Request = json.loads(Raw.decode("utf-8"))
        Cmd     = Request.get("Cmd", "")

        if Cmd == "GET_BLOCK":
            Index = Request.get("Index", -1)
            Path  = os.path.join(BLOCKS_DIR, f"block_{Index}.json")
            if os.path.exists(Path):
                with open(Path, "r") as F:
                    Block = json.load(F)
                Conn.sendall(json.dumps(Block).encode("utf-8"))
            else:
                Conn.sendall(b"NOT_FOUND")

        elif Cmd == "CHAIN_LEN":
            Files  = [F for F in os.listdir(BLOCKS_DIR) if F.startswith("block_") and F.endswith(".json")] if os.path.exists(BLOCKS_DIR) else []
            Length = len(Files)
            Conn.sendall(json.dumps({"Length": Length}).encode("utf-8"))

    except Exception as E:
        print(f"  [Sync] Handler Error: {E}")
    finally:
        Conn.close()

def Start_Sync_Server(Blocks_Dir_Override=None):
    global BLOCKS_DIR
    if Blocks_Dir_Override:
        BLOCKS_DIR = Blocks_Dir_Override

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", SYNC_PORT))
    Srv.listen(20)

    def Accept_Loop():
        while True:
            try:
                Conn, _ = Srv.accept()
                T = threading.Thread(target=Handle_Sync_Request, args=(Conn,), daemon=True)
                T.start()
            except Exception:
                break

    T = threading.Thread(target=Accept_Loop, daemon=True)
    T.start()
    return Srv
