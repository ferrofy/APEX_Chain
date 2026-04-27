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
def SHA256(T): return hashlib.sha256(T.encode()).hexdigest()

def Make_Genesis(IP):
    T = time.time(); D = {"Message": "Genesis Block", "Node": IP}
    return {"Index": 0, "Timestamp": T, "Data": D, "Previous_Hash": None, "Hash": "0" * 64}

def Make_Block(Prev, Msg, IP):
    I = Prev["Index"] + 1; T = time.time()
    D = {"Message": Msg, "Node": IP, "Time": datetime.utcnow().isoformat()}
    H = SHA256(f"{I}{T}{json.dumps(D, sort_keys=True)}{Prev['Hash']}")
    return {"Index": I, "Timestamp": T, "Data": D, "Previous_Hash": Prev["Hash"], "Hash": H}

def Save_Block(B):
    os.makedirs(FOLDER, exist_ok=True)
    with open(os.path.join(FOLDER, f"{B['Index']}.json"), "w") as F:
        json.dump(B, F, indent=4)

def Load_Chain():
    C = []
    if not os.path.exists(FOLDER): return C
    for F in os.listdir(FOLDER):
        if F.endswith(".json"):
            try:
                with open(os.path.join(FOLDER, F)) as Fh: C.append(json.load(Fh))
            except: pass
    C.sort(key=lambda B: B["Index"]); return C

def Get_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP

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
            if T == "Chain_Length_Request":
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

def Add_Peer(Sock, IP):
    P = Make_Peer(IP, Sock)
    with Peers_Lock: Peers.append(P)
    Log(f"Node {IP} Connected")
    threading.Thread(target=Peer_Reader, args=(P,), daemon=True).start()
    return P

def Broadcast(B):
    with Peers_Lock: Active = list(Peers)
    for P in Active:
        try: Send_Msg(P["Sock"], P["Lock"], {"Type": "Block", "Data": B})
        except: pass

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

def Start_TX():
    global My_IP
    os.makedirs(FOLDER, exist_ok=True)
    My_IP = Get_IP()
    print("\n" + "=" * 50)
    print("   ⬡  FerroFy  |  TX Origin Node")
    print("=" * 50)
    Log(f"IP: {My_IP} | Port: {PORT}")
    Loaded = Load_Chain()
    if Loaded:
        with Chain_Lock: Chain.extend(Loaded)
        Log(f"Loaded {len(Loaded)} Block(s) From Disk")
    else:
        G = Make_Genesis(My_IP)
        with Chain_Lock: Chain.append(G)
        Save_Block(G)
        Log(f"Genesis Created | Hash: {G['Hash'][:16]}...")
    threading.Thread(target=Run_Server, daemon=True).start()
    Log("Server Listening For Peer Connections")
    print("-" * 50 + "\n")
    Log("Type A Message And Press Enter To Mine\n")
    while True:
        try:
            Msg = input("📝  Message > ").strip()
            if not Msg: continue
            with Chain_Lock: Prev = Chain[-1]
            B = Make_Block(Prev, Msg, My_IP)
            with Chain_Lock: Chain.append(B)
            Save_Block(B)
            Log(f"Block {B['Index']} Mined | Hash: {B['Hash'][:16]}...")
            Log(f"Prev Hash       | {B['Previous_Hash'][:16]}...")
            Broadcast(B)
            with Peers_Lock: Cnt = len(Peers)
            Log(f"Broadcast To {Cnt} Node(s)\n")
        except KeyboardInterrupt:
            Log("TX Node Shutting Down"); break

Start_TX()