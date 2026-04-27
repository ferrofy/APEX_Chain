import socket, threading, time, json, os, hashlib, sys, queue
from datetime import datetime

PORT   = 5000
FOLDER = "Blocks"
HS_SRV = "FerroFy_SRV"
HS_CLI = "FerroFy_CLI"

Connected_Clients = []; Clients_Lock = threading.Lock()

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

def Make_Genesis(IP):
    T = time.time(); D = {"Message": "Genesis Block", "Node": IP}
    H = SHA256(f"0{T}{json.dumps(D, sort_keys=True)}{'0'*64}")
    return {"Index": 0, "Timestamp": T, "Data": D, "Previous_Hash": "0"*64, "Hash": H}

def Make_Block(Prev, Msg, IP):
    I = Prev["Index"]+1; T = time.time()
    D = {"Message": Msg, "Node": IP, "Time": datetime.utcnow().isoformat()}
    H = SHA256(f"{I}{T}{json.dumps(D, sort_keys=True)}{Prev['Hash']}")
    return {"Index": I, "Timestamp": T, "Data": D, "Previous_Hash": Prev["Hash"], "Hash": H}

def Get_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP

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

def Broadcast(Msg, Chain):
    with Clients_Lock: Cl = list(Connected_Clients)
    Dead = []
    for Entry in Cl:
        try: Send_Msg(Entry["Sock"], Entry["Lock"], Msg)
        except: Dead.append(Entry)
    with Clients_Lock:
        for E in Dead: Connected_Clients.remove(E) if E in Connected_Clients else None

def Handle_Client(Sock, Addr, Chain):
    print(f"[Connecting] {Addr[0]}")
    try:
        Sock.settimeout(3.0); Sock.send(HS_SRV.encode())
        if Sock.recv(64).decode() != HS_CLI: Sock.close(); return
        Sock.settimeout(None)
    except: Sock.close(); return
    Entry = {"Sock": Sock, "Lock": threading.Lock(), "IP": Addr[0], "Pending": {}, "PLock": threading.Lock()}
    with Clients_Lock: Connected_Clients.append(Entry)
    print(f"[Auth OK] {Addr[0]} Verified — Syncing {len(Chain)} Block(s)")
    for B in Chain:
        try: Send_Msg(Sock, Entry["Lock"], {"Type":"Block","Data":B}); time.sleep(0.05)
        except: break
    while True:
        try:
            M = Recv_Msg(Sock)
            if not M: break
            if M.get("Type") == "Request_Block":
                Idx = M["Index"]
                B = next((b for b in Chain if b["Index"]==Idx), None)
                Send_Msg(Sock, Entry["Lock"], {"Type":"Block_Response","Index":Idx,"Block":B})
                print(f"[Block Request] Sent Block {Idx} To {Addr[0]}")
        except: break
    with Clients_Lock:
        if Entry in Connected_Clients: Connected_Clients.remove(Entry)
    print(f"[Disconnected] {Addr[0]}")

def Verify_Before_Mine(Chain):
    Bad = Validate_Chain(Chain)
    if Bad:
        print(f"[Verify Failed] Bad Indices: {Bad} — Fix Before Mining")
        return False
    return True

def Mine_Loop(Chain, My_IP):
    print(f"\n[TX Node Ready] IP: {My_IP} | Chain: {len(Chain)} Block(s)")
    print("[Ready] Type A Message And Press Enter To Mine\n")
    while True:
        try:
            Msg = input("📝 Message > ").strip()
            if not Msg: print("[Skip] Empty Message"); continue
            if not Verify_Before_Mine(Chain):
                print("[Blocked] Fix Chain Issues First"); continue
            Prev = Chain[-1]
            B = Make_Block(Prev, Msg, My_IP)
            Chain.append(B)
            Save_Block(B)
            print(f"[Mined] {B['Index']}.json | Hash: {B['Hash'][:16]}...")
            print(f"[Chained] Prev: {Prev['Hash'][:16]}...")
            Broadcast({"Type":"Block","Data":B}, Chain)
            with Clients_Lock:
                Cnt = len(Connected_Clients)
            print(f"[Broadcast] Sent To {Cnt} Connected Node(s)\n")
        except KeyboardInterrupt:
            print("\n[Shutdown] TX Node Stopped"); break

def Start_TX():
    My_IP = Get_IP()
    os.makedirs(FOLDER, exist_ok=True)
    Chain = Load_Chain()
    if not Chain:
        G = Make_Genesis(My_IP); Chain.append(G); Save_Block(G)
        print(f"[Genesis] Block 0 Created | Hash: {G['Hash'][:16]}...")
    else:
        print(f"[Loaded] {len(Chain)} Block(s) From Disk")
        Bad = Validate_Chain(Chain)
        if Bad: print(f"[Warning] Corrupt Blocks At: {Bad}")
        else: print("[Verified] All Blocks Valid ✓")
    SRV = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SRV.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    SRV.bind(("0.0.0.0", PORT)); SRV.listen(50)
    print(f"[Server] Listening On {My_IP}:{PORT}")
    def Accept():
        while True:
            try:
                C, A = SRV.accept()
                threading.Thread(target=Handle_Client, args=(C, A, Chain), daemon=True).start()
            except: pass
    threading.Thread(target=Accept, daemon=True).start()
    Mine_Loop(Chain, My_IP)

Start_TX()