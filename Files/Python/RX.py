import socket, threading, time, json, os, hashlib
from datetime import datetime

PORT   = 5000
FOLDER = "Blocks"
HS_SRV = "FerroFy_SRV"
HS_CLI = "FerroFy_CLI"

Chain = []; Chain_Lock = threading.Lock()
Peers = []; Peers_Lock = threading.Lock()
My_IP = "127.0.0.1"

def Log(Msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {Msg}")

def Save_Block(B):
    os.makedirs(FOLDER, exist_ok=True)
    with open(os.path.join(FOLDER, f"{B['Index']}.json"), "w") as F:
        json.dump(B, F, indent=4)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP, ".".join(IP.split(".")[:-1]) + "."

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

def Make_Peer(IP, Sock):
    return {"IP": IP, "Sock": Sock, "Lock": threading.Lock(),
            "Pending": {}, "PLock": threading.Lock(),
            "Chain_Len": None, "Len_Ev": threading.Event()}

def Peer_Reader(P):
    while True:
        try:
            M = Recv_Msg(P["Sock"])
            if not M: break
            T = M.get("Type")
            if T == "Block":
                On_Block(M["Data"])
            elif T == "Chain_Length_Request":
                with Chain_Lock: L = len(Chain)
                Send_Msg(P["Sock"], P["Lock"], {"Type": "Chain_Length", "Length": L})
            elif T == "Chain_Length":
                P["Chain_Len"] = M["Length"]; P["Len_Ev"].set()
            elif T == "Request_Block":
                Idx = M["Index"]
                with Chain_Lock: B = next((b for b in Chain if b["Index"] == Idx), None)
                Send_Msg(P["Sock"], P["Lock"], {"Type": "Block_Response", "Index": Idx, "Block": B})
            elif T == "Block_Response":
                with P["PLock"]:
                    E = P["Pending"].get(M["Index"])
                    if E: E["Data"] = M["Block"]; E["Ev"].set()
        except: break
    with Peers_Lock:
        if P in Peers: Peers.remove(P)
    Log(f"Node {P['IP']} Disconnected")

def On_Block(B):
    with Chain_Lock:
        if any(x["Index"] == B["Index"] for x in Chain): return
        Chain.append(B); Chain.sort(key=lambda b: b["Index"])
    Save_Block(B)
    Log(f"Block {B['Index']} Received | Hash: {B['Hash'][:16]}...")

def Add_Peer(Sock, IP):
    P = Make_Peer(IP, Sock)
    with Peers_Lock: Peers.append(P)
    Log(f"Node {IP} Connected")
    threading.Thread(target=Peer_Reader, args=(P,), daemon=True).start()
    return P

def Handle_Incoming(Sock, Addr):
    try:
        Sock.settimeout(3.0); Sock.send(HS_SRV.encode())
        if Sock.recv(64).decode() != HS_CLI: Sock.close(); return
        Sock.settimeout(None)
    except: Sock.close(); return
    P = Add_Peer(Sock, Addr[0])
    with Chain_Lock: Snap = list(Chain)
    for B in Snap:
        try: Send_Msg(P["Sock"], P["Lock"], {"Type": "Block", "Data": B}); time.sleep(0.05)
        except: break

def Run_Server():
    SRV = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SRV.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    SRV.bind(("0.0.0.0", PORT)); SRV.listen(50)
    while True:
        try:
            C, A = SRV.accept()
            threading.Thread(target=Handle_Incoming, args=(C, A), daemon=True).start()
        except: pass

def Connect_To(IP):
    try:
        S = socket.socket(); S.settimeout(3.0); S.connect((IP, PORT))
        if S.recv(64).decode() != HS_SRV: S.close(); return False
        S.send(HS_CLI.encode()); S.settimeout(None)
        Add_Peer(S, IP); return True
    except: return False

def Scan_Network(My_IP, Prefix):
    Found = []; Lk = threading.Lock()
    def Try(IP):
        try:
            S = socket.socket(); S.settimeout(0.3); S.connect((IP, PORT)); S.close()
            with Lk: Found.append(IP)
        except: pass
    Ths = [threading.Thread(target=Try, args=(f"{Prefix}{i}",), daemon=True)
           for i in range(1, 255) if f"{Prefix}{i}" != My_IP]
    for T in Ths: T.start()
    for T in Ths: T.join()
    return Found

def Consensus_Sync():
    with Peers_Lock: Active = list(Peers)
    if not Active: return
    Log(f"Consensus Sync With {len(Active)} Peer(s)...")
    for P in Active:
        P["Len_Ev"].clear(); P["Chain_Len"] = None
        try: Send_Msg(P["Sock"], P["Lock"], {"Type": "Chain_Length_Request"})
        except: pass
    for P in Active: P["Len_Ev"].wait(timeout=3.0)
    Lengths = [P["Chain_Len"] for P in Active if P["Chain_Len"] is not None]
    if not Lengths: Log("No Responses — Sync Aborted"); return
    Vote = {}
    for L in Lengths: Vote[L] = Vote.get(L, 0) + 1
    Target = max(Vote, key=Vote.get)
    Log(f"Network Chain Length: {Target}")
    New_Chain = []
    for Idx in range(Target):
        Votes = {}; Evs = []
        for P in Active:
            Ev = threading.Event(); Entry = {"Ev": Ev, "Data": None}
            with P["PLock"]: P["Pending"][Idx] = Entry
            try: Send_Msg(P["Sock"], P["Lock"], {"Type": "Request_Block", "Index": Idx})
            except: Ev.set()
            Evs.append((P, Entry))
        for P, Entry in Evs:
            Entry["Ev"].wait(timeout=4.0)
            with P["PLock"]: P["Pending"].pop(Idx, None)
            if Entry["Data"] is not None:
                K = json.dumps(Entry["Data"], sort_keys=True)
                Votes[K] = Votes.get(K, 0) + 1
        if not Votes: Log(f"Block {Idx}: No Response"); break
        Best = max(Votes, key=Votes.get)
        if Votes[Best] / len(Active) >= 0.5:
            New_Chain.append(json.loads(Best))
            Log(f"Block {Idx} Accepted — {Votes[Best]}/{len(Active)} Majority")
        else:
            Log(f"Block {Idx}: No Majority — Stopping"); break
    if New_Chain:
        with Chain_Lock: Chain.clear(); Chain.extend(New_Chain)
        for B in New_Chain: Save_Block(B)
        Log(f"Chain Synced — {len(New_Chain)} Block(s)")

def Start_RX():
    global My_IP
    os.makedirs(FOLDER, exist_ok=True)
    My_IP, Prefix = Get_Local_Info()
    print("\n" + "=" * 50)
    print("   ⬡  FerroFy  |  RX Receiver Node")
    print("=" * 50)
    Log(f"IP: {My_IP} | Port: {PORT}")
    threading.Thread(target=Run_Server, daemon=True).start()
    Log("Server Started — Accepting Incoming Peers")
    print("-" * 50)
    while True:
        Log("Scanning For TX Nodes...")
        Found = Scan_Network(My_IP, Prefix)
        if not Found:
            Log("No Nodes Found — Retrying In 60 Seconds"); time.sleep(60); continue
        Log(f"Found {len(Found)} Node(s)")
        Connected = 0
        for IP in Found:
            if Connect_To(IP):
                Log(f"Connected To {IP}"); Connected += 1
        if not Connected:
            Log("No Verified Connections — Retrying In 60 Seconds"); time.sleep(60); continue
        time.sleep(0.5)
        Consensus_Sync()
        Log(f"Chain Ready — {len(Chain)} Block(s)")
        print("-" * 50 + "\n")
        try:
            while True:
                time.sleep(5)
                with Peers_Lock: Alive = len(Peers)
                if Alive == 0: Log("All Peers Lost — Rescanning..."); break
        except KeyboardInterrupt:
            Log("RX Node Shutting Down"); break

Start_RX()