import socket, os, threading, time, json, hashlib

Port   = 5000
Folder = "Blocks"

Chain      = []
Chain_Lock = threading.Lock()
Server_Peer = None
Server_Lock  = threading.Lock()

def Init_Folder():
    os.makedirs(Folder, exist_ok=True)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:    S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    Prefix = ".".join(IP.split(".")[:-1]) + "."
    return IP, Prefix

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

def Compute_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Load_Chain():
    Blocks = []
    if not os.path.exists(Folder): return Blocks
    for F in os.listdir(Folder):
        if not F.endswith(".json"): continue
        try:
            with open(os.path.join(Folder, F)) as Fh:
                Blocks.append(json.load(Fh))
        except: pass
    Blocks.sort(key=lambda B: B["Index"])
    return Blocks

def Save_Block(Block):
    with open(os.path.join(Folder, f"{Block['Index']}.json"), "w") as F:
        json.dump(Block, F, indent=4)

def Verify_Full_Chain(Snap):
    Bad = []
    for i, B in enumerate(Snap):
        Recomputed = Compute_Hash(B["Index"], B["Timestamp"], B["Data"], B["Previous_Hash"])
        if Recomputed != B["Hash"]:
            Bad.append(B["Index"]); continue
        if i > 0 and B["Previous_Hash"] != Snap[i-1]["Hash"]:
            Bad.append(B["Index"])
    return Bad

def Send_Msg(Sock, Lock, Msg):
    P = json.dumps(Msg).encode()
    with Lock: Sock.sendall(len(P).to_bytes(4, "big") + P)

def Recv_Msg(Sock):
    H = b""
    while len(H) < 4:
        C = Sock.recv(4 - len(H))
        if not C: return None
        H += C
    N = int.from_bytes(H, "big"); D = b""
    while len(D) < N:
        C = Sock.recv(min(8192, N - len(D)))
        if not C: return None
        D += C
    return json.loads(D.decode())

def Request_Block_From_Server(Idx):
    global Server_Peer
    with Server_Lock: Peer = Server_Peer
    if not Peer: print(f"[Repair] Not Connected To Server"); return None
    Ev = threading.Event()
    Entry = {"Ev": Ev, "Block": None}
    with Peer["PLock"]: Peer["Pending"][Idx] = Entry
    try:    Send_Msg(Peer["Sock"], Peer["Lock"], {"Type": "Request_Block", "Index": Idx})
    except:
        with Peer["PLock"]: Peer["Pending"].pop(Idx, None)
        return None
    Ev.wait(timeout=5.0)
    with Peer["PLock"]: Peer["Pending"].pop(Idx, None)
    B = Entry["Block"]
    if B: print(f"[Repair] Block {Idx} Received From Server"); return B
    print(f"[Repair] Block {Idx}: No Response"); return None

def Consensus_Repair(Bad_Indices):
    print(f"[Repair] Fixing Blocks: {Bad_Indices}")
    for Idx in sorted(Bad_Indices):
        Fixed = Request_Block_From_Server(Idx)
        if Fixed:
            Recomputed = Compute_Hash(Fixed["Index"], Fixed["Timestamp"], Fixed["Data"], Fixed["Previous_Hash"])
            if Recomputed != Fixed["Hash"]:
                print(f"[Repair] Block {Idx} From Server Is Corrupt — Skipping"); continue
            Save_Block(Fixed)
            with Chain_Lock:
                New = [B for B in Chain if B["Index"] != Idx]
                New.append(Fixed); New.sort(key=lambda B: B["Index"])
                Chain.clear(); Chain.extend(New)
            print(f"[Repair] Block {Idx} Restored ✓")
        else:
            print(f"[Repair] Block {Idx} Lost — Server Could Not Help")

def Ingest_Block(B):
    with Chain_Lock:
        Already = any(X["Index"] == B["Index"] for X in Chain)
    if Already: return
    Recomputed = Compute_Hash(B["Index"], B["Timestamp"], B["Data"], B["Previous_Hash"])
    if Recomputed != B["Hash"]:
        print(f"[Reject] Block {B['Index']} — Hash Invalid"); return
    with Chain_Lock:
        if Chain and B["Index"] == Chain[-1]["Index"] + 1 and B["Previous_Hash"] != Chain[-1]["Hash"]:
            print(f"[Reject] Block {B['Index']} — PrevHash Mismatch"); return
        Chain.append(B); Chain.sort(key=lambda X: X["Index"])
    Save_Block(B)
    print(f"[Received] Block {B['Index']} | Hash: {B['Hash'][:20]}... ✓")

def Server_Reader(Peer):
    global Server_Peer
    while True:
        try:
            Msg = Recv_Msg(Peer["Sock"])
            if not Msg: break
            T = Msg.get("Type")
            if T == "Block":
                Ingest_Block(Msg["Data"])
            elif T == "Request_Block":
                Idx = Msg["Index"]
                with Chain_Lock:
                    Block = next((B for B in Chain if B["Index"] == Idx), None)
                Send_Msg(Peer["Sock"], Peer["Lock"], {"Type": "Block_Response", "Index": Idx, "Block": Block})
            elif T == "Block_Response":
                Idx = Msg["Index"]
                with Peer["PLock"]:
                    Entry = Peer["Pending"].get(Idx)
                    if Entry: Entry["Block"] = Msg.get("Block"); Entry["Ev"].set()
        except: break
    with Server_Lock: Server_Peer = None
    print("[Disconnected] Lost Connection To Server")

def Connect_To_Server(IP):
    global Server_Peer
    print(f"[Connecting] To {IP}:{Port}...")
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(3.0); S.connect((IP, Port))
        Greeting = S.recv(1024).decode()
        if Greeting != "Mine_RX":
            print("[Auth Failed] Wrong Server Greeting"); S.close(); return False
        S.send("Mine_TX".encode()); S.settimeout(None)
    except Exception as E:
        print(f"[Connect Failed] {E}"); return False
    Peer = {"IP": IP, "Sock": S, "Lock": threading.Lock(), "Pending": {}, "PLock": threading.Lock()}
    with Server_Lock: Server_Peer = Peer
    threading.Thread(target=Server_Reader, args=(Peer,), daemon=True).start()
    print(f"[Auth OK] Connected To {IP} As Receiver")
    return True

def Scan_And_Connect():
    My_IP, Prefix = Get_Local_Info()
    Found = []; Lk = threading.Lock()
    def Try(IP):
        try:
            S = socket.socket(); S.settimeout(0.3); S.connect((IP, Port)); S.close()
            with Lk: Found.append(IP)
        except: pass
    Ths = [threading.Thread(target=Try, args=(f"{Prefix}{i}",), daemon=True)
           for i in range(1, 255) if f"{Prefix}{i}" != My_IP]
    print("[Scanning] 15-Second Discovery Window...")
    Start = time.time()
    while time.time() - Start < 15:
        for T in Ths: T.start()
        for T in Ths: T.join()
        if Found: break
        Ths = [threading.Thread(target=Try, args=(f"{Prefix}{i}",), daemon=True)
               for i in range(1, 255) if f"{Prefix}{i}" != My_IP]
        time.sleep(0.5)
    return Found

def Start_Client():
    Init_Folder()
    Loaded = Load_Chain()
    with Chain_Lock: Chain.extend(Loaded)
    if Loaded:
        print(f"[Loaded] {len(Loaded)} Local Block(s)")
        Bad = Verify_Full_Chain(Loaded)
        if Bad: print(f"[Verify] ✗ Local Issues At: {Bad} — Will Repair After Connect")
        else:   print(f"[Verify] ✓ Local Chain Valid")
    while True:
        Found = Scan_And_Connect()
        if Found:
            for IP in Found:
                if Connect_To_Server(IP): break
            with Server_Lock: Connected = Server_Peer is not None
            if Connected:
                time.sleep(2.0)
                with Chain_Lock: Snap = list(Chain)
                Bad = Verify_Full_Chain(Snap)
                if Bad:
                    print(f"[Verify] ✗ Repairing {len(Bad)} Block(s) Via Server...")
                    Consensus_Repair(Bad)
                else:
                    print(f"[Verify] ✓ Chain Fully Valid — {len(Snap)} Block(s)")
                while True:
                    with Server_Lock: Still = Server_Peer is not None
                    if not Still:
                        print("[Retry] Server Lost — Rescanning..."); break
                    time.sleep(5)
        else:
            print("[Timeout] No Nodes Found. Retrying In 60 Seconds...")
            time.sleep(60)

Start_Client()