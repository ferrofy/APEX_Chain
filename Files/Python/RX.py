import socket, threading, time, json, os, hashlib
from datetime import datetime

PORT   = 5000
FOLDER = "Blocks"
HS_SRV = "FerroFy_SRV"
HS_CLI = "FerroFy_CLI"

Chain = []; Chain_Lock = threading.Lock()
Peers = []; Peers_Lock = threading.Lock()

def SHA256(T):
    return hashlib.sha256(T.encode()).hexdigest()

def Block_Hash(B):
    Raw = f"{B['Index']}{B['Timestamp']}{json.dumps(B['Data'], sort_keys=True)}{B['Previous_Hash']}"
    return SHA256(Raw)

def Validate_Chain(C):
    Bad = []
    for i, B in enumerate(C):
        if Block_Hash(B) != B["Hash"]: Bad.append(i); continue
        if i > 0 and B["Previous_Hash"] != C[i-1]["Hash"]: Bad.append(i)
    return Bad

def Load_Chain():
    C = []
    if not os.path.exists(FOLDER): return C
    for F in os.listdir(FOLDER):
        if F.endswith(".json"):
            try:
                with open(os.path.join(FOLDER, F)) as Fh: C.append(json.load(Fh))
            except: pass
    C.sort(key=lambda B: B["Index"]); return C

def Save_Block(B):
    os.makedirs(FOLDER, exist_ok=True)
    with open(os.path.join(FOLDER, f"{B['Index']}.json"), "w") as F:
        json.dump(B, F, indent=4)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: S.connect(("8.8.8.8",80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP, ".".join(IP.split(".")[:-1])+"."

def Send_Msg(Sock, Lock, Msg):
    P = json.dumps(Msg).encode()
    with Lock: Sock.sendall(len(P).to_bytes(4,"big") + P)

def Recv_Msg(Sock):
    H = b""
    while len(H)<4:
        C = Sock.recv(4-len(H))
        if not C: return None
        H += C
    N = int.from_bytes(H,"big"); D = b""
    while len(D)<N:
        C = Sock.recv(min(8192, N-len(D)))
        if not C: return None
        D += C
    return json.loads(D.decode())

def Add_Peer(Sock, IP):
    P = {"IP": IP, "Sock": Sock, "Lock": threading.Lock(), "Pending": {}, "PLock": threading.Lock()}
    with Peers_Lock: Peers.append(P)
    print(f"[Peer Added] {IP}")
    threading.Thread(target=Peer_Reader, args=(P,), daemon=True).start()
    return P

def Peer_Reader(P):
    while True:
        try:
            M = Recv_Msg(P["Sock"])
            if not M: break
            T = M.get("Type")
            if T == "Block":
                Ingest_Block(M["Data"])
            elif T == "Block_Response":
                with P["PLock"]:
                    E = P["Pending"].get(M["Index"])
                    if E: E["Data"] = M["Block"]; E["Ev"].set()
        except: break
    with Peers_Lock:
        if P in Peers: Peers.remove(P)
    print(f"[Disconnected] Peer {P['IP']}")

def Ingest_Block(B):
    with Chain_Lock:
        if any(x["Index"]==B["Index"] for x in Chain): return
        Is_Valid = (Block_Hash(B)==B["Hash"] and
                    (not Chain or (B["Index"]==Chain[-1]["Index"]+1 and B["Previous_Hash"]==Chain[-1]["Hash"])))
    if Is_Valid:
        with Chain_Lock: Chain.append(B)
        Save_Block(B)
        print(f"[Saved] {B['Index']}.json | Hash: {B['Hash'][:16]}...")
    else:
        print(f"[Invalid] Block {B['Index']} — Requesting Repair From Peers")
        threading.Thread(target=Repair_Block, args=(B["Index"],), daemon=True).start()

def Repair_Block(Idx):
    with Peers_Lock: Active = list(Peers)
    if not Active: print(f"[Repair] Block {Idx}: No Peers Available"); return
    print(f"[Repair] Block {Idx} — Querying {len(Active)} Peer(s)...")
    Votes = {}
    for P in Active:
        Ev = threading.Event(); Entry = {"Ev": Ev, "Data": None}
        with P["PLock"]: P["Pending"][Idx] = Entry
        try: Send_Msg(P["Sock"], P["Lock"], {"Type":"Request_Block","Index":Idx})
        except: continue
        Ev.wait(timeout=5.0)
        with P["PLock"]: P["Pending"].pop(Idx, None)
        if Entry["Data"]:
            K = json.dumps(Entry["Data"], sort_keys=True)
            Votes[K] = Votes.get(K, 0) + 1
    if not Votes: print(f"[Repair] Block {Idx}: No Responses"); return
    Best = max(Votes, key=Votes.get)
    if Votes[Best] / len(Active) >= 0.5:
        W = json.loads(Best)
        with Chain_Lock:
            New = [x for x in Chain if x["Index"]!=Idx] + [W]
            New.sort(key=lambda b: b["Index"])
            Chain.clear(); Chain.extend(New)
        Save_Block(W)
        print(f"[Repaired] Block {Idx} — {Votes[Best]}/{len(Active)} Majority")
    else:
        print(f"[Repair] Block {Idx}: No 50% Majority — Keeping Local")

def Verify_And_Repair():
    with Chain_Lock: Bad = Validate_Chain(Chain)
    if not Bad: print("[Verify] All Blocks Valid ✓"); return
    print(f"[Verify] Bad Indices: {Bad} — Requesting From Peers")
    for Idx in Bad:
        threading.Thread(target=Repair_Block, args=(Idx,), daemon=True).start()

def Connect_To(IP):
    try:
        S = socket.socket(); S.settimeout(3.0); S.connect((IP, PORT))
        if S.recv(64).decode() != HS_SRV: S.close(); return False
        S.send(HS_CLI.encode()); S.settimeout(None)
        P = Add_Peer(S, IP)
        return True
    except: return False

def Scan_And_Connect(My_IP, Prefix):
    Found = []; Lk = threading.Lock()
    def Try(IP):
        try:
            S = socket.socket(); S.settimeout(0.3); S.connect((IP, PORT)); S.close()
            with Lk: Found.append(IP)
        except: pass
    Ths = []
    for i in range(1, 255):
        IP = f"{Prefix}{i}"
        if IP == My_IP: continue
        T = threading.Thread(target=Try, args=(IP,), daemon=True); Ths.append(T); T.start()
    for T in Ths: T.join()
    return Found

def Start_RX():
    global Chain
    os.makedirs(FOLDER, exist_ok=True)
    My_IP, Prefix = Get_Local_Info()
    print(f"[RX Node] IP: {My_IP}")
    Chain = Load_Chain()
    if Chain: print(f"[Loaded] {len(Chain)} Block(s) From Disk")
    else: print("[Empty] No Local Blocks")
    while True:
        print("[Scanning] Looking For TX Nodes...")
        Found = Scan_And_Connect(My_IP, Prefix)
        if Found:
            print(f"[Found] {len(Found)} Node(s) On Network")
            Connected = 0
            for IP in Found:
                if Connect_To(IP): Connected += 1
            if Connected:
                print(f"[Connected] {Connected} Node(s) Verified")
                print("[Verifying] Checking Local Chain...")
                time.sleep(2.0)
                Verify_And_Repair()
                print("[Running] Receiving Blocks...")
                while True:
                    time.sleep(5)
                    with Peers_Lock: Alive = len(Peers)
                    if Alive == 0: print("[Lost] All Peers Disconnected — Rescanning..."); break
            else:
                print("[Retry] No Verified Connections — Sleeping 60s...")
                time.sleep(60)
        else:
            print("[Timeout] No TX Nodes Found — Sleeping 60s...")
            time.sleep(60)

Start_RX()