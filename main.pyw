import tkinter as tk
from tkinter import ttk
import socket, threading, time, json, os, hashlib, sys, queue
from datetime import datetime

PORT   = 5000
FOLDER = "Blocks"
HS_SRV = "FerroFy_SRV"
HS_CLI = "FerroFy_CLI"

BG = "#07091C"; PANEL = "#0C0F26"; CARD = "#111535"; BORDER = "#1E2448"
INDIGO = "#4F46E5"; CYAN = "#06B6D4"; GREEN = "#10B981"; RED = "#EF4444"
AMBER = "#F59E0B"; TEXT = "#E2E8F0"; MUTED = "#6B7280"

Chain = []; Chain_Lock = threading.Lock()
Peers = []; Peers_Lock = threading.Lock()
Mode = "TX"; My_IP = "127.0.0.1"
Log_Q = queue.Queue(); Update_Q = queue.Queue()

def SHA256(T):
    return hashlib.sha256(T.encode()).hexdigest()

def Block_Hash(B):
    Raw = f"{B['Index']}{B['Timestamp']}{json.dumps(B['Data'], sort_keys=True)}{B['Previous_Hash']}"
    return SHA256(Raw)

def Validate_Chain(C):
    Bad = []
    for i, B in enumerate(C):
        if Block_Hash(B) != B["Hash"]:
            Bad.append(i); continue
        if i > 0 and B["Previous_Hash"] != C[i-1]["Hash"]:
            Bad.append(i)
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

def Log(Msg, Lvl="INFO"):
    Log_Q.put({"Msg": Msg, "Lvl": Lvl, "T": datetime.now().strftime("%H:%M:%S")})

def Notify(Kind):
    Update_Q.put(Kind)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: S.connect(("8.8.8.8",80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP, ".".join(IP.split(".")[:-1])+"."

def Add_Peer(Sock, IP):
    P = {"IP": IP, "Sock": Sock, "Lock": threading.Lock(), "Pending": {}, "PLock": threading.Lock()}
    with Peers_Lock: Peers.append(P)
    Log(f"Node {IP} Connected", "OK")
    threading.Thread(target=Peer_Reader, args=(P,), daemon=True).start()
    Notify("Peers"); return P

def Peer_Reader(P):
    while True:
        try:
            M = Recv_Msg(P["Sock"])
            if not M: break
            T = M.get("Type")
            if T == "Block":
                Ingest_Block(M["Data"])
            elif T == "Request_Block":
                Idx = M["Index"]
                with Chain_Lock: B = next((b for b in Chain if b["Index"]==Idx), None)
                Send_Msg(P["Sock"], P["Lock"], {"Type":"Block_Response","Index":Idx,"Block":B})
            elif T == "Block_Response":
                with P["PLock"]:
                    E = P["Pending"].get(M["Index"])
                    if E: E["Data"] = M["Block"]; E["Ev"].set()
        except: break
    with Peers_Lock:
        if P in Peers: Peers.remove(P)
    Log(f"Node {P['IP']} Disconnected", "WARN"); Notify("Peers")

def Ingest_Block(B):
    with Chain_Lock:
        if any(x["Index"]==B["Index"] for x in Chain): return
        Valid = (Block_Hash(B)==B["Hash"] and
                 (not Chain or (B["Index"]==Chain[-1]["Index"]+1 and B["Previous_Hash"]==Chain[-1]["Hash"])))
    if Valid:
        with Chain_Lock: Chain.append(B)
        Save_Block(B)
        Log(f"Block {B['Index']} Saved | {B['Hash'][:12]}...", "OK"); Notify("Chain")
    else:
        Log(f"Block {B['Index']} Invalid — Requesting Repair", "WARN")
        threading.Thread(target=Repair_Block, args=(B["Index"],), daemon=True).start()

def Repair_Block(Idx):
    with Peers_Lock: Active = list(Peers)
    if not Active: Log(f"Block {Idx}: No Peers To Query", "ERROR"); return
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
    if not Votes: Log(f"Block {Idx}: No Peer Response", "ERROR"); return
    Best = max(Votes, key=Votes.get)
    if Votes[Best] / len(Active) >= 0.5:
        W = json.loads(Best)
        with Chain_Lock:
            New = [x for x in Chain if x["Index"]!=Idx] + [W]
            New.sort(key=lambda b: b["Index"])
            Chain.clear(); Chain.extend(New)
        Save_Block(W)
        Log(f"Block {Idx} Fixed — {Votes[Best]}/{len(Active)} Majority", "OK"); Notify("Chain")
    else:
        Log(f"Block {Idx}: No 50% Majority Reached", "ERROR")

def Verify_And_Repair():
    with Chain_Lock: Bad = Validate_Chain(Chain)
    if not Bad: Log("Chain Verified ✓  All Blocks Valid", "OK"); return
    Log(f"Issues At Indices: {Bad}", "WARN")
    for Idx in Bad:
        threading.Thread(target=Repair_Block, args=(Idx,), daemon=True).start()

def Mine_Block(Msg):
    with Chain_Lock:
        Bad = Validate_Chain(Chain); Prev = Chain[-1]
    if Bad:
        Log("Chain Invalid — Repairing Before Mine...", "WARN")
        Verify_And_Repair(); return
    B = Make_Block(Prev, Msg, My_IP)
    with Chain_Lock: Chain.append(B)
    Save_Block(B)
    Log(f"Block {B['Index']} Mined | {B['Hash'][:12]}...", "OK"); Notify("Chain")
    with Peers_Lock: P_Copy = list(Peers)
    for P in P_Copy:
        try: Send_Msg(P["Sock"], P["Lock"], {"Type":"Block","Data":B})
        except: pass

def Handle_Client(Sock, Addr):
    try:
        Sock.settimeout(3.0); Sock.send(HS_SRV.encode())
        if Sock.recv(64).decode() != HS_CLI: Sock.close(); return
        Sock.settimeout(None)
    except: Sock.close(); return
    P = Add_Peer(Sock, Addr[0])
    with Chain_Lock: Snap = list(Chain)
    for B in Snap:
        try: Send_Msg(P["Sock"], P["Lock"], {"Type":"Block","Data":B}); time.sleep(0.05)
        except: break

def Run_Server():
    SRV = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SRV.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    SRV.bind(("0.0.0.0", PORT)); SRV.listen(50)
    Log(f"Listening On {My_IP}:{PORT}", "OK")
    while True:
        try:
            C, A = SRV.accept()
            threading.Thread(target=Handle_Client, args=(C, A), daemon=True).start()
        except: pass

def Connect_To(IP):
    try:
        S = socket.socket(); S.settimeout(3.0); S.connect((IP, PORT))
        if S.recv(64).decode() != HS_SRV: S.close(); return
        S.send(HS_CLI.encode()); S.settimeout(None)
        Add_Peer(S, IP); Log(f"Connected To {IP}", "OK")
    except: pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FerroFy Blockchain Node")
        self.geometry("1200x760"); self.minsize(960, 620)
        self.configure(bg=BG)
        self._Build(); self.after(120, self._Poll); self.after(800, self._Pulse)

    def _Build(self):
        self._Header(); Main = tk.Frame(self, bg=BG)
        Main.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self._Left(Main); self._Right(Main); self._Bottom()

    def _Header(self):
        H = tk.Frame(self, bg=PANEL, height=58); H.pack(fill="x", padx=10, pady=10)
        H.pack_propagate(False)
        tk.Label(H, text="⬡  FerroFy Blockchain", font=("Segoe UI",15,"bold"), bg=PANEL, fg=TEXT).pack(side="left", padx=18)
        self.Mode_L = tk.Label(H, text=f"● {Mode}", font=("Segoe UI",11,"bold"), bg=PANEL, fg=CYAN)
        self.Mode_L.pack(side="left", padx=8)
        self.IP_L = tk.Label(H, text=f"IP: {My_IP}", font=("Consolas",10), bg=PANEL, fg=MUTED)
        self.IP_L.pack(side="left", padx=14)
        self.Peer_L = tk.Label(H, text="0 Nodes", font=("Segoe UI",10), bg=PANEL, fg=MUTED)
        self.Peer_L.pack(side="right", padx=18)
        self.Chain_L = tk.Label(H, text="0 Blocks", font=("Segoe UI",10), bg=PANEL, fg=MUTED)
        self.Chain_L.pack(side="right", padx=10)
        self.Dot = tk.Label(H, text="●", font=("Segoe UI",15), bg=PANEL, fg=GREEN)
        self.Dot.pack(side="right", padx=4)

    def _Left(self, P):
        LF = tk.Frame(P, bg=PANEL, width=300); LF.pack(side="left", fill="y", padx=(0,6))
        LF.pack_propagate(False)
        tk.Label(LF, text="Block Explorer", font=("Segoe UI",11,"bold"), bg=PANEL, fg=TEXT).pack(padx=14, pady=(14,6), anchor="w")
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        LB_Frame = tk.Frame(LF, bg=PANEL); LB_Frame.pack(fill="both", expand=True, padx=4, pady=6)
        SB = ttk.Scrollbar(LB_Frame)
        self.BList = tk.Listbox(LB_Frame, bg=PANEL, fg=TEXT, selectbackground=INDIGO, selectforeground=TEXT,
                                 font=("Consolas",10), bd=0, highlightthickness=0, activestyle="none",
                                 yscrollcommand=SB.set, cursor="hand2")
        SB.config(command=self.BList.yview)
        self.BList.pack(side="left", fill="both", expand=True)
        SB.pack(side="right", fill="y")
        self.BList.bind("<<ListboxSelect>>", self._Sel)
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        tk.Button(LF, text="🔍  Verify Chain", font=("Segoe UI",10), bg=CARD, fg=CYAN, bd=0,
                  padx=10, pady=7, cursor="hand2", activebackground=INDIGO, activeforeground=TEXT,
                  command=lambda: threading.Thread(target=Verify_And_Repair, daemon=True).start()
                  ).pack(fill="x", padx=14, pady=10)

    def _Right(self, P):
        RF = tk.Frame(P, bg=BG); RF.pack(side="left", fill="both", expand=True)
        self.DFrame = tk.Frame(RF, bg=CARD, height=270); self.DFrame.pack(fill="x", pady=(0,6))
        self.DFrame.pack_propagate(False)
        tk.Label(self.DFrame, text="Block Detail", font=("Segoe UI",11,"bold"), bg=CARD, fg=TEXT).pack(padx=14, pady=(12,5), anchor="w")
        tk.Frame(self.DFrame, bg=BORDER, height=1).pack(fill="x", padx=14)
        self.DText = tk.Text(self.DFrame, bg=CARD, fg=TEXT, font=("Consolas",10), bd=0,
                              highlightthickness=0, wrap="word", state="disabled", cursor="arrow")
        self.DText.pack(fill="both", expand=True, padx=14, pady=10)
        for Tag, Clr in [("key",CYAN),("val",TEXT),("hash",INDIGO),("ok",GREEN),("err",RED)]:
            self.DText.tag_config(Tag, foreground=Clr)
        NF = tk.Frame(RF, bg=PANEL, height=80); NF.pack(fill="x", pady=(0,6))
        NF.pack_propagate(False)
        tk.Label(NF, text="Connected Nodes", font=("Segoe UI",10,"bold"), bg=PANEL, fg=TEXT).pack(padx=14, pady=(8,4), anchor="w")
        self.NText = tk.Text(NF, bg=PANEL, fg=MUTED, font=("Consolas",9), bd=0, highlightthickness=0, height=2, state="disabled")
        self.NText.pack(fill="x", padx=14)
        LF = tk.Frame(RF, bg=PANEL); LF.pack(fill="both", expand=True)
        tk.Label(LF, text="Activity Log", font=("Segoe UI",10,"bold"), bg=PANEL, fg=TEXT).pack(padx=14, pady=(10,4), anchor="w")
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        self.LText = tk.Text(LF, bg=PANEL, fg=TEXT, font=("Consolas",9), bd=0, highlightthickness=0, state="disabled", wrap="word")
        self.LText.pack(fill="both", expand=True, padx=6, pady=6)
        for Tag, Clr in [("OK",GREEN),("ERROR",RED),("WARN",AMBER),("INFO",CYAN),("t",MUTED)]:
            self.LText.tag_config(Tag, foreground=Clr)

    def _Bottom(self):
        BF = tk.Frame(self, bg=PANEL, height=62); BF.pack(fill="x", padx=10, pady=(0,10))
        BF.pack_propagate(False)
        tk.Label(BF, text="📝", font=("Segoe UI",14), bg=PANEL).pack(side="left", padx=(14,5))
        self.Entry = tk.Entry(BF, font=("Segoe UI",12), bg=CARD, fg=TEXT, insertbackground=TEXT,
                               bd=0, highlightthickness=1, highlightcolor=INDIGO, highlightbackground=BORDER)
        self.Entry.pack(side="left", fill="both", expand=True, padx=10, pady=13)
        self.Entry.bind("<Return>", self._Mine)
        State = "normal" if Mode == "TX" else "disabled"
        Lbl = "⛏  Mine Block" if Mode == "TX" else "⟳  RX Mode"
        tk.Button(BF, text=Lbl, font=("Segoe UI",11,"bold"), bg=INDIGO, fg=TEXT, bd=0,
                  padx=20, cursor="hand2", activebackground="#6366F1", activeforeground=TEXT,
                  state=State, command=self._Mine).pack(side="right", padx=14, pady=13)

    def _Mine(self, _=None):
        Msg = self.Entry.get().strip()
        if not Msg: return
        self.Entry.delete(0, "end")
        threading.Thread(target=Mine_Block, args=(Msg,), daemon=True).start()

    def _Sel(self, _):
        Sel = self.BList.curselection()
        if not Sel: return
        try: Idx = int(self.BList.get(Sel[0]).split()[1].rstrip(":"))
        except: return
        with Chain_Lock: B = next((b for b in Chain if b["Index"]==Idx), None)
        if not B: return
        self.DText.config(state="normal"); self.DText.delete("1.0","end")
        Ts = datetime.fromtimestamp(B["Timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        for K, V in [("Index",str(B["Index"])),("Timestamp",Ts),("Message",B["Data"].get("Message","")),
                     ("Node",B["Data"].get("Node","")),("Hash",B["Hash"]),("Prev Hash",B["Previous_Hash"])]:
            self.DText.insert("end", f"  {K}:  ","key")
            self.DText.insert("end", f"{V}\n","hash" if "Hash" in K else "val")
        with Chain_Lock: Bad = Validate_Chain(Chain)
        self.DText.insert("end","\n  Status:  ","key")
        self.DText.insert("end","✓ Valid\n" if Idx not in Bad else "✗ Hash Mismatch\n","ok" if Idx not in Bad else "err")
        self.DText.config(state="disabled")

    def _Refresh_Chain(self):
        with Chain_Lock: C = list(Chain); Bad = Validate_Chain(C)
        Cur = list(self.BList.get(0,"end"))
        New = [f"  Block {B['Index']}:  {B['Data'].get('Message','')[:28]}" for B in C]
        if Cur != New:
            self.BList.delete(0,"end")
            for i, It in enumerate(New):
                self.BList.insert("end", It)
                self.BList.itemconfig(i, fg=RED if i in Bad else GREEN)
        self.Chain_L.config(text=f"{len(C)} Block(s)")
        self.Dot.config(fg=RED if Bad else GREEN)

    def _Refresh_Peers(self):
        with Peers_Lock: IPs = [P["IP"] for P in Peers]
        self.Peer_L.config(text=f"{len(IPs)} Node(s)")
        self.NText.config(state="normal"); self.NText.delete("1.0","end")
        self.NText.insert("end","  " + ("  ●  ".join(IPs) if IPs else "No Peers Connected"))
        self.NText.config(state="disabled")

    def _Poll(self):
        while not Log_Q.empty():
            E = Log_Q.get_nowait()
            self.LText.config(state="normal")
            self.LText.insert("end", f"[{E['T']}] ","t")
            self.LText.insert("end", f"{E['Msg']}\n", E["Lvl"])
            self.LText.see("end"); self.LText.config(state="disabled")
        while not Update_Q.empty():
            K = Update_Q.get_nowait()
            if K == "Chain": self._Refresh_Chain()
            elif K == "Peers": self._Refresh_Peers()
        self.after(120, self._Poll)

    def _Pulse(self):
        C = self.Dot.cget("fg")
        self.Dot.config(fg=MUTED if C != MUTED else (RED if Validate_Chain(Chain) else GREEN))
        self.after(900, self._Pulse)

def Startup():
    global My_IP, Mode, Chain
    os.makedirs(FOLDER, exist_ok=True)
    My_IP, Prefix = Get_Local_Info()
    Log(f"Node IP: {My_IP}", "INFO")
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
    Chain = Load_Chain()
    if not Chain:
        G = Make_Genesis(My_IP); Chain.append(G); Save_Block(G)
        Log("Genesis Block Created", "OK")
    else:
        Log(f"Loaded {len(Chain)} Block(s) From Disk", "OK")
    threading.Thread(target=Run_Server, daemon=True).start()
    if Found:
        Mode = "RX"
        Log(f"Found {len(Found)} Node(s) — Joining As Receiver", "INFO")
        for IP in Found:
            threading.Thread(target=Connect_To, args=(IP,), daemon=True).start()
    else:
        Mode = "TX"
        Log("No Nodes Found — Starting As Origin (TX)", "INFO")
    threading.Thread(target=Verify_And_Repair, daemon=True).start()

if __name__ == "__main__":
    Startup()
    App_Win = App()
    App_Win.Mode_L.config(text=f"● {Mode}")
    App_Win.IP_L.config(text=f"IP: {My_IP}")
    App_Win.mainloop()