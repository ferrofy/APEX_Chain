import socket, os, threading, time, json, hashlib

Host   = "0.0.0.0"
Port   = 5000
Folder = "Blocks"

Chain            = []
Chain_Lock       = threading.Lock()
Connected_Clients = []
Clients_Lock     = threading.Lock()

def Init_Folder():
    os.makedirs(Folder, exist_ok=True)

def Get_Local_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:    S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP

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

def Request_Block_From_Peers(Idx):
    with Clients_Lock: Peers = list(Connected_Clients)
    if not Peers:
        print(f"[Repair] No Peers For Block {Idx}"); return None
    Total = len(Peers); Votes = {}
    for Peer in Peers:
        Ev = threading.Event()
        Entry = {"Ev": Ev, "Block": None}
        with Peer["PLock"]: Peer["Pending"][Idx] = Entry
        try:    Send_Msg(Peer["Sock"], Peer["Lock"], {"Type": "Request_Block", "Index": Idx})
        except:
            with Peer["PLock"]: Peer["Pending"].pop(Idx, None); continue
        Ev.wait(timeout=5.0)
        with Peer["PLock"]: Peer["Pending"].pop(Idx, None)
        B = Entry["Block"]
        if B:
            Key = json.dumps(B, sort_keys=True)
            Votes[Key] = Votes.get(Key, 0) + 1
    if not Votes: print(f"[Repair] Block {Idx}: No Response"); return None
    Best_Key = max(Votes, key=Votes.get); Best_N = Votes[Best_Key]
    print(f"[Consensus] Block {Idx}: {Best_N}/{Total} Majority Votes")
    if Best_N / Total >= 0.5: return json.loads(Best_Key)
    print(f"[Repair] Block {Idx}: Under 50% — Cannot Fix"); return None

def Consensus_Repair(Bad_Indices):
    print(f"[Repair] Fixing Blocks: {Bad_Indices}")
    for Idx in sorted(Bad_Indices):
        Fixed = Request_Block_From_Peers(Idx)
        if Fixed:
            Save_Block(Fixed)
            with Chain_Lock:
                New = [B for B in Chain if B["Index"] != Idx]
                New.append(Fixed); New.sort(key=lambda B: B["Index"])
                Chain.clear(); Chain.extend(New)
            print(f"[Repair] Block {Idx} Restored ✓")
        else:
            print(f"[Repair] Block {Idx} Lost — No Consensus")

def Client_Reader(Peer):
    while True:
        try:
            Msg = Recv_Msg(Peer["Sock"])
            if not Msg: break
            T = Msg.get("Type")
            if T == "Request_Block":
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
    with Clients_Lock:
        if Peer in Connected_Clients: Connected_Clients.remove(Peer)
    print(f"[Disconnected] {Peer['IP']} Left")

def Broadcast_Block(Block):
    Dead = []
    with Clients_Lock: Peers = list(Connected_Clients)
    for Peer in Peers:
        try:    Send_Msg(Peer["Sock"], Peer["Lock"], {"Type": "Block", "Data": Block})
        except: Dead.append(Peer)
    with Clients_Lock:
        for D in Dead:
            if D in Connected_Clients: Connected_Clients.remove(D)

def Handle_Client(Sock, Addr):
    print(f"\n[Connected] {Addr[0]} — Verifying...")
    try:
        Sock.settimeout(2.0); Sock.send("Mine_RX".encode())
        if Sock.recv(1024).decode() != "Mine_TX":
            print(f"[Auth Failed] {Addr[0]}"); Sock.close(); return
        Sock.settimeout(None); print(f"[Auth OK] {Addr[0]} Is Verified Peer")
    except:
        print(f"[Auth Failed] Handshake Dropped — {Addr[0]}"); Sock.close(); return
    Peer = {"IP": Addr[0], "Sock": Sock, "Lock": threading.Lock(), "Pending": {}, "PLock": threading.Lock()}
    with Clients_Lock: Connected_Clients.append(Peer)
    threading.Thread(target=Client_Reader, args=(Peer,), daemon=True).start()
    with Chain_Lock: Snap = list(Chain)
    for Block in Snap:
        try:    Send_Msg(Peer["Sock"], Peer["Lock"], {"Type": "Block", "Data": Block}); time.sleep(0.05)
        except: break

def Build_Genesis(Node_IP):
    T = time.time(); D = {"Message": "Genesis Block", "Node": Node_IP}
    H = Compute_Hash(0, T, D, "0" * 64)
    return {"Index": 0, "Timestamp": T, "Data": D, "Previous_Hash": "0" * 64, "Hash": H}

def Build_Next(Prev, Msg, Node_IP):
    I = Prev["Index"] + 1; T = time.time()
    D = {"Message": Msg, "Node": Node_IP, "Block_Time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(T))}
    H = Compute_Hash(I, T, D, Prev["Hash"])
    return {"Index": I, "Timestamp": T, "Data": D, "Previous_Hash": Prev["Hash"], "Hash": H}

def Mine_Block(Msg, Node_IP):
    print("\n[Verify] Checking Full Chain Before Mining...")
    with Chain_Lock: Snap = list(Chain)
    Bad = Verify_Full_Chain(Snap)
    if Bad:
        print(f"[Verify] ✗ Bad Blocks: {Bad}")
        Consensus_Repair(Bad)
        with Chain_Lock: Snap = list(Chain)
        Still_Bad = Verify_Full_Chain(Snap)
        if Still_Bad:
            print(f"[Abort] Chain Still Broken At {Still_Bad} — Mining Cancelled"); return
    else:
        print(f"[Verify] ✓ {len(Snap)} Block(s) All Valid")
    with Chain_Lock: Prev = Chain[-1]
    New = Build_Next(Prev, Msg, Node_IP)
    with Chain_Lock: Chain.append(New)
    Save_Block(New)
    print(f"[Mined]  Block {New['Index']}  | Hash:     {New['Hash'][:20]}...")
    print(f"[Chain]  Linked To {Prev['Index']} | PrevHash: {Prev['Hash'][:20]}...")
    Broadcast_Block(New)

def Accept_Loop(Srv):
    while True:
        try:
            Sock, Addr = Srv.accept(); Sock.settimeout(None)
            threading.Thread(target=Handle_Client, args=(Sock, Addr), daemon=True).start()
        except: pass

def Start_Server():
    Init_Folder()
    Node_IP = Get_Local_IP()
    Loaded = Load_Chain()
    if not Loaded:
        G = Build_Genesis(Node_IP)
        with Chain_Lock: Chain.append(G)
        Save_Block(G)
        print(f"[Genesis] Block 0 Created | Hash: {G['Hash'][:20]}...")
    else:
        with Chain_Lock: Chain.extend(Loaded)
        print(f"[Loaded]  {len(Loaded)} Block(s) From '{Folder}/'")
        Bad = Verify_Full_Chain(Loaded)
        if Bad: print(f"[Verify] ✗ Issues At: {Bad} — Will Repair When Peers Connect")
        else:   print(f"[Verify] ✓ Chain Valid")
    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind((Host, Port)); Srv.listen(100)
    print(f"[Server]  {Node_IP}:{Port} — Ready\n")
    threading.Thread(target=Accept_Loop, args=(Srv,), daemon=True).start()
    while True:
        try:
            Msg = input("📝 Message > ").strip()
            if not Msg: print("[Skip] Empty Message"); continue
            Mine_Block(Msg, Node_IP)
        except KeyboardInterrupt:
            print("\n[Shutdown] TX Node Stopped"); break

Start_Server()