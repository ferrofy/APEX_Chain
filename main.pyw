import tkinter as tk
from tkinter import ttk
import socket, threading, time, json, os, hashlib, queue
from datetime import datetime

PORT   = 5000
FOLDER = "Blocks"
HS_SRV = "Mine_RX"
HS_CLI = "Mine_TX"

BG     = "#07091C"
PANEL  = "#0C0F26"
CARD   = "#111535"
BORDER = "#1E2448"
INDIGO = "#4F46E5"
CYAN   = "#06B6D4"
GREEN  = "#10B981"
RED    = "#EF4444"
AMBER  = "#F59E0B"
TEXT   = "#E2E8F0"
MUTED  = "#6B7280"
PURPLE = "#8B5CF6"

Chain       = []
Chain_Lock  = threading.Lock()
Peers       = []
Peers_Lock  = threading.Lock()
Mode        = "TX"
My_IP       = "127.0.0.1"
Log_Q       = queue.Queue()
Update_Q    = queue.Queue()

def SHA256(T):
    return hashlib.sha256(T.encode()).hexdigest()

def Compute_Hash(Index, Timestamp, Data, Prev):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Prev}"
    return SHA256(Raw)

def Verify_Full_Chain(Snap):
    Bad = []
    for i, B in enumerate(Snap):
        Recomp = Compute_Hash(B["Index"], B["Timestamp"], B["Data"], B["Previous_Hash"])
        if Recomp != B["Hash"]:
            Bad.append(B["Index"]); continue
        if i > 0 and B["Previous_Hash"] != Snap[i-1]["Hash"]:
            Bad.append(B["Index"])
    return Bad

def Load_Chain():
    C = []
    if not os.path.exists(FOLDER): return C
    for F in os.listdir(FOLDER):
        if not F.endswith(".json"): continue
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
    H = Compute_Hash(0, T, D, "0" * 64)
    return {"Index": 0, "Timestamp": T, "Data": D, "Previous_Hash": "0" * 64, "Hash": H}

def Make_Block(Prev, Msg, IP):
    I = Prev["Index"] + 1; T = time.time()
    D = {"Message": Msg, "Node": IP, "Time": datetime.utcnow().isoformat()}
    H = Compute_Hash(I, T, D, Prev["Hash"])
    return {"Index": I, "Timestamp": T, "Data": D, "Previous_Hash": Prev["Hash"], "Hash": H}

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

def Log(Msg, Lvl="INFO"):
    Log_Q.put({"Msg": Msg, "Lvl": Lvl, "T": datetime.now().strftime("%H:%M:%S")})

def Notify(Kind):
    Update_Q.put(Kind)

def Get_Local_Info():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:    S.connect(("8.8.8.8", 80)); IP = S.getsockname()[0]
    except: IP = "127.0.0.1"
    finally: S.close()
    return IP, ".".join(IP.split(".")[:-1]) + "."

def Add_Peer(Sock, IP):
    P = {"IP": IP, "Sock": Sock, "Lock": threading.Lock(), "Pending": {}, "PLock": threading.Lock()}
    with Peers_Lock: Peers.append(P)
    Log(f"Node {IP} Joined The Network", "OK")
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
                with Chain_Lock: B = next((b for b in Chain if b["Index"] == Idx), None)
                Send_Msg(P["Sock"], P["Lock"], {"Type": "Block_Response", "Index": Idx, "Block": B})
            elif T == "Block_Response":
                with P["PLock"]:
                    E = P["Pending"].get(M["Index"])
                    if E: E["Data"] = M["Block"]; E["Ev"].set()
        except: break
    with Peers_Lock:
        if P in Peers: Peers.remove(P)
    Log(f"Node {P['IP']} Disconnected", "WARN"); Notify("Peers")

def Ingest_Block(B):
    Recomp = Compute_Hash(B["Index"], B["Timestamp"], B["Data"], B["Previous_Hash"])
    if Recomp != B["Hash"]:
        Log(f"Block {B['Index']} Rejected — Hash Invalid", "ERROR"); return
    with Chain_Lock:
        if any(x["Index"] == B["Index"] for x in Chain): return
        if Chain and B["Index"] == Chain[-1]["Index"] + 1 and B["Previous_Hash"] != Chain[-1]["Hash"]:
            Log(f"Block {B['Index']} Rejected — PrevHash Mismatch", "ERROR")
            threading.Thread(target=Repair_Block, args=(B["Index"] - 1,), daemon=True).start(); return
        Chain.append(B); Chain.sort(key=lambda x: x["Index"])
    Save_Block(B)
    Log(f"Block {B['Index']} Accepted | {B['Hash'][:14]}...", "OK"); Notify("Chain")

def Request_Block_From_Peers(Idx):
    with Peers_Lock: Active = list(Peers)
    if not Active: Log(f"Block {Idx}: No Peers To Query", "ERROR"); return None
    Votes = {}; Total = len(Active)
    for P in Active:
        Ev = threading.Event(); Entry = {"Ev": Ev, "Data": None}
        with P["PLock"]: P["Pending"][Idx] = Entry
        try:    Send_Msg(P["Sock"], P["Lock"], {"Type": "Request_Block", "Index": Idx})
        except:
            with P["PLock"]: P["Pending"].pop(Idx, None); continue
        Ev.wait(timeout=5.0)
        with P["PLock"]: P["Pending"].pop(Idx, None)
        if Entry["Data"]:
            K = json.dumps(Entry["Data"], sort_keys=True)
            Votes[K] = Votes.get(K, 0) + 1
    if not Votes: return None
    Best = max(Votes, key=Votes.get); Count = Votes[Best]
    Log(f"Block {Idx} Consensus: {Count}/{Total} Votes", "INFO")
    if Count / Total >= 0.5: return json.loads(Best)
    Log(f"Block {Idx}: No 50% Majority", "ERROR"); return None

def Repair_Block(Idx):
    Log(f"Repairing Block {Idx}...", "WARN")
    W = Request_Block_From_Peers(Idx)
    if not W: Log(f"Block {Idx}: Cannot Repair — No Consensus", "ERROR"); return
    Recomp = Compute_Hash(W["Index"], W["Timestamp"], W["Data"], W["Previous_Hash"])
    if Recomp != W["Hash"]: Log(f"Block {Idx}: Consensus Block Is Corrupt", "ERROR"); return
    with Chain_Lock:
        New = [x for x in Chain if x["Index"] != Idx]
        New.append(W); New.sort(key=lambda b: b["Index"])
        Chain.clear(); Chain.extend(New)
    Save_Block(W)
    Log(f"Block {Idx} Restored Via Consensus ✓", "OK"); Notify("Chain")

def Verify_And_Repair():
    with Chain_Lock: Snap = list(Chain)
    Bad = Verify_Full_Chain(Snap)
    if not Bad:
        Log(f"Full Chain Verified ✓  All {len(Snap)} Blocks Valid", "OK"); return
    Log(f"Chain Issues At Indices: {Bad} — Requesting Repairs", "WARN")
    for Idx in Bad:
        threading.Thread(target=Repair_Block, args=(Idx,), daemon=True).start()

def Mine_Block(Msg):
    Log("Verifying Chain Before Mining...", "INFO")
    with Chain_Lock: Snap = list(Chain)
    Bad = Verify_Full_Chain(Snap)
    if Bad:
        Log(f"Chain Invalid At {Bad} — Repairing First...", "WARN")
        Verify_And_Repair()
        with Chain_Lock: Snap = list(Chain)
        if Verify_Full_Chain(Snap):
            Log("Chain Still Broken — Mining Aborted", "ERROR"); return
    with Chain_Lock: Prev = Chain[-1]
    B = Make_Block(Prev, Msg, My_IP)
    with Chain_Lock: Chain.append(B)
    Save_Block(B)
    Log(f"Block {B['Index']} Mined | {B['Hash'][:14]}...", "OK"); Notify("Chain")
    with Peers_Lock: P_Copy = list(Peers)
    for P in P_Copy:
        try:    Send_Msg(P["Sock"], P["Lock"], {"Type": "Block", "Data": B})
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
        try:    Send_Msg(P["Sock"], P["Lock"], {"Type": "Block", "Data": B}); time.sleep(0.05)
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
        Add_Peer(S, IP)
    except: pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FerroFy — Blockchain Node")
        self.geometry("1280x780"); self.minsize(1000, 640)
        self.configure(bg=BG)
        self._Build()
        self.after(150, self._Poll)
        self.after(900, self._Pulse)
        self.after(300, self._Refresh_All)

    def _Build(self):
        self._Header()
        Main = tk.Frame(self, bg=BG)
        Main.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._Left(Main); self._Right(Main)
        self._Bottom()

    def _Header(self):
        H = tk.Frame(self, bg=PANEL, height=62)
        H.pack(fill="x", padx=12, pady=12); H.pack_propagate(False)
        Logo = tk.Label(H, text="⬡  FerroFy Blockchain", font=("Segoe UI", 15, "bold"), bg=PANEL, fg=TEXT)
        Logo.pack(side="left", padx=20)
        self.Mode_Badge = tk.Label(H, text=f"● {Mode}", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=CYAN)
        self.Mode_Badge.pack(side="left", padx=6)
        self.IP_Label = tk.Label(H, text=f"  {My_IP}", font=("Consolas", 10), bg=PANEL, fg=MUTED)
        self.IP_Label.pack(side="left", padx=10)
        self.Dot = tk.Label(H, text="●", font=("Segoe UI", 16), bg=PANEL, fg=GREEN)
        self.Dot.pack(side="right", padx=6)
        self.Block_Count = tk.Label(H, text="0 Blocks", font=("Segoe UI", 10), bg=PANEL, fg=MUTED)
        self.Block_Count.pack(side="right", padx=10)
        self.Peer_Count = tk.Label(H, text="0 Nodes", font=("Segoe UI", 10), bg=PANEL, fg=MUTED)
        self.Peer_Count.pack(side="right", padx=10)

    def _Left(self, Parent):
        LF = tk.Frame(Parent, bg=PANEL, width=310)
        LF.pack(side="left", fill="y", padx=(0, 8)); LF.pack_propagate(False)
        Hdr = tk.Frame(LF, bg=PANEL); Hdr.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(Hdr, text="Block Explorer", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=TEXT).pack(side="left")
        self.Chain_Status = tk.Label(Hdr, text="✓", font=("Segoe UI", 11, "bold"), bg=PANEL, fg=GREEN)
        self.Chain_Status.pack(side="right")
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        LB_F = tk.Frame(LF, bg=PANEL); LB_F.pack(fill="both", expand=True, padx=4, pady=6)
        SB = ttk.Scrollbar(LB_F)
        self.BList = tk.Listbox(LB_F, bg=CARD, fg=TEXT, selectbackground=INDIGO, selectforeground=TEXT,
                                 font=("Consolas", 10), bd=0, highlightthickness=0, activestyle="none",
                                 yscrollcommand=SB.set, cursor="hand2")
        SB.config(command=self.BList.yview)
        self.BList.pack(side="left", fill="both", expand=True)
        SB.pack(side="right", fill="y")
        self.BList.bind("<<ListboxSelect>>", self._On_Select)
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        Btn_F = tk.Frame(LF, bg=PANEL); Btn_F.pack(fill="x", padx=14, pady=10)
        tk.Button(Btn_F, text="🔍  Verify Chain", font=("Segoe UI", 10), bg=CARD, fg=CYAN,
                  bd=0, padx=10, pady=7, cursor="hand2", activebackground=INDIGO, activeforeground=TEXT,
                  command=lambda: threading.Thread(target=Verify_And_Repair, daemon=True).start()
                  ).pack(fill="x", pady=(0, 4))
        tk.Button(Btn_F, text="🔄  Repair Chain", font=("Segoe UI", 10), bg=CARD, fg=AMBER,
                  bd=0, padx=10, pady=7, cursor="hand2", activebackground="#92400E", activeforeground=TEXT,
                  command=self._Force_Repair).pack(fill="x")

    def _Right(self, Parent):
        RF = tk.Frame(Parent, bg=BG); RF.pack(side="left", fill="both", expand=True)
        DF = tk.Frame(RF, bg=CARD, height=260); DF.pack(fill="x", pady=(0, 6)); DF.pack_propagate(False)
        tk.Label(DF, text="Block Detail", font=("Segoe UI", 11, "bold"), bg=CARD, fg=TEXT).pack(padx=14, pady=(12, 5), anchor="w")
        tk.Frame(DF, bg=BORDER, height=1).pack(fill="x", padx=14)
        self.Detail = tk.Text(DF, bg=CARD, fg=TEXT, font=("Consolas", 10), bd=0,
                               highlightthickness=0, wrap="word", state="disabled", cursor="arrow")
        self.Detail.pack(fill="both", expand=True, padx=14, pady=10)
        for Tag, Clr in [("key", CYAN), ("val", TEXT), ("hash", PURPLE), ("ok", GREEN), ("err", RED), ("warn", AMBER)]:
            self.Detail.tag_config(Tag, foreground=Clr)
        NF = tk.Frame(RF, bg=PANEL, height=72); NF.pack(fill="x", pady=(0, 6)); NF.pack_propagate(False)
        tk.Label(NF, text="Connected Peers", font=("Segoe UI", 10, "bold"), bg=PANEL, fg=TEXT).pack(padx=14, pady=(8, 2), anchor="w")
        self.Peers_Text = tk.Text(NF, bg=PANEL, fg=MUTED, font=("Consolas", 9), bd=0,
                                    highlightthickness=0, height=2, state="disabled")
        self.Peers_Text.pack(fill="x", padx=14)
        LF = tk.Frame(RF, bg=PANEL); LF.pack(fill="both", expand=True)
        tk.Label(LF, text="Activity Log", font=("Segoe UI", 10, "bold"), bg=PANEL, fg=TEXT).pack(padx=14, pady=(10, 4), anchor="w")
        tk.Frame(LF, bg=BORDER, height=1).pack(fill="x", padx=14)
        self.Log_Text = tk.Text(LF, bg=PANEL, fg=TEXT, font=("Consolas", 9), bd=0,
                                  highlightthickness=0, state="disabled", wrap="word")
        self.Log_Text.pack(fill="both", expand=True, padx=6, pady=6)
        for Tag, Clr in [("OK", GREEN), ("ERROR", RED), ("WARN", AMBER), ("INFO", CYAN), ("t", MUTED)]:
            self.Log_Text.tag_config(Tag, foreground=Clr)

    def _Bottom(self):
        BF = tk.Frame(self, bg=PANEL, height=66)
        BF.pack(fill="x", padx=12, pady=(0, 12)); BF.pack_propagate(False)
        tk.Label(BF, text="📝", font=("Segoe UI", 14), bg=PANEL).pack(side="left", padx=(16, 6))
        self.Entry = tk.Entry(BF, font=("Segoe UI", 12), bg=CARD, fg=TEXT, insertbackground=TEXT,
                               bd=0, highlightthickness=1, highlightcolor=INDIGO, highlightbackground=BORDER)
        self.Entry.pack(side="left", fill="both", expand=True, padx=10, pady=14)
        self.Entry.bind("<Return>", self._Mine)
        State = "normal" if Mode == "TX" else "disabled"
        Label = "⛏  Mine Block" if Mode == "TX" else "◉  RX — Read Only"
        Fg    = INDIGO if Mode == "TX" else MUTED
        tk.Button(BF, text=Label, font=("Segoe UI", 11, "bold"), bg=Fg, fg=TEXT, bd=0,
                  padx=22, cursor="hand2" if Mode == "TX" else "arrow",
                  activebackground="#6366F1", activeforeground=TEXT,
                  state=State, command=self._Mine).pack(side="right", padx=16, pady=14)

    def _Mine(self, _=None):
        Msg = self.Entry.get().strip()
        if not Msg: return
        self.Entry.delete(0, "end")
        threading.Thread(target=Mine_Block, args=(Msg,), daemon=True).start()

    def _Force_Repair(self):
        with Chain_Lock: Snap = list(Chain)
        Bad = Verify_Full_Chain(Snap)
        if not Bad: Log("Chain Is Already Valid — Nothing To Repair", "OK"); return
        for Idx in Bad:
            threading.Thread(target=Repair_Block, args=(Idx,), daemon=True).start()

    def _On_Select(self, _):
        Sel = self.BList.curselection()
        if not Sel: return
        try:
            Raw = self.BList.get(Sel[0])
            Idx = int(Raw.split()[1].rstrip(":"))
        except: return
        with Chain_Lock: B = next((b for b in Chain if b["Index"] == Idx), None)
        if not B: return
        self.Detail.config(state="normal"); self.Detail.delete("1.0", "end")
        Ts  = datetime.fromtimestamp(B["Timestamp"]).strftime("%Y-%m-%d  %H:%M:%S")
        Msg = B["Data"].get("Message", "—")
        Node = B["Data"].get("Node", "—")
        BT   = B["Data"].get("Time", B["Data"].get("Block_Time", "—"))
        for K, V, Tag in [
            ("Index",       str(B["Index"]),    "val"),
            ("Timestamp",   Ts,                 "val"),
            ("Message",     Msg,                "val"),
            ("Node",        Node,               "val"),
            ("Block Time",  BT,                 "val"),
            ("Hash",        B["Hash"],          "hash"),
            ("Prev Hash",   B["Previous_Hash"], "hash"),
        ]:
            self.Detail.insert("end", f"  {K:<14}", "key")
            self.Detail.insert("end", f"  {V}\n", Tag)
        self.Detail.insert("end", "\n")
        with Chain_Lock: Snap = list(Chain)
        Bad = Verify_Full_Chain(Snap)
        self.Detail.insert("end", "  Status       ", "key")
        if Idx in Bad:
            self.Detail.insert("end", "  ✗ Hash Mismatch / Broken Link\n", "err")
        else:
            self.Detail.insert("end", "  ✓ Block Valid\n", "ok")
        self.Detail.config(state="disabled")

    def _Refresh_All(self):
        self._Refresh_Chain(); self._Refresh_Peers()
        self.after(300, self._Refresh_All)

    def _Refresh_Chain(self):
        with Chain_Lock: C = list(Chain)
        Bad = Verify_Full_Chain(C)
        New = [f"  Block {B['Index']}:  {B['Data'].get('Message','')[:30]}" for B in C]
        Cur = list(self.BList.get(0, "end"))
        if Cur != New:
            self.BList.delete(0, "end")
            for i, It in enumerate(New):
                self.BList.insert("end", It)
                self.BList.itemconfig(i, fg=RED if i in Bad else GREEN)
        self.Block_Count.config(text=f"{len(C)} Block(s)")
        self.Chain_Status.config(text="✗" if Bad else "✓", fg=RED if Bad else GREEN)

    def _Refresh_Peers(self):
        with Peers_Lock: IPs = [P["IP"] for P in Peers]
        self.Peer_Count.config(text=f"{len(IPs)} Node(s)")
        self.Peers_Text.config(state="normal"); self.Peers_Text.delete("1.0", "end")
        self.Peers_Text.insert("end", "  " + ("  ●  ".join(IPs) if IPs else "No Peers Connected"))
        self.Peers_Text.config(state="disabled")

    def _Poll(self):
        while not Log_Q.empty():
            E = Log_Q.get_nowait()
            self.Log_Text.config(state="normal")
            self.Log_Text.insert("end", f"[{E['T']}] ", "t")
            self.Log_Text.insert("end", f"{E['Msg']}\n", E["Lvl"])
            self.Log_Text.see("end"); self.Log_Text.config(state="disabled")
        while not Update_Q.empty():
            K = Update_Q.get_nowait()
            if K == "Chain":  self._Refresh_Chain()
            elif K == "Peers": self._Refresh_Peers()
        self.after(150, self._Poll)

    def _Pulse(self):
        with Chain_Lock: Snap = list(Chain)
        Bad = Verify_Full_Chain(Snap)
        C   = self.Dot.cget("fg")
        Next = (RED if Bad else GREEN) if C == MUTED else MUTED
        self.Dot.config(fg=Next)
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
    Log("Scanning Network For Peers...", "INFO")
    for T in Ths: T.join()
    Chain = Load_Chain()
    if not Chain:
        G = Make_Genesis(My_IP); Chain.append(G); Save_Block(G)
        Log("Genesis Block Created", "OK")
    else:
        Log(f"Loaded {len(Chain)} Block(s) From Disk", "OK")
        Bad = Verify_Full_Chain(Chain)
        if Bad: Log(f"Chain Issues At: {Bad} — Will Repair After Peers Connect", "WARN")
        else:   Log("Local Chain Valid ✓", "OK")
    threading.Thread(target=Run_Server, daemon=True).start()
    if Found:
        Mode = "RX"
        Log(f"Found {len(Found)} Peer(s) — Joining As Receiver", "INFO")
        for IP in Found:
            threading.Thread(target=Connect_To, args=(IP,), daemon=True).start()
    else:
        Mode = "TX"
        Log("No Peers Found — Starting As Origin Miner (TX)", "INFO")
    threading.Thread(target=Verify_And_Repair, daemon=True).start()


if __name__ == "__main__":
    Startup()
    App_Win = App()
    App_Win.Mode_Badge.config(text=f"● {Mode}", fg=CYAN if Mode == "TX" else AMBER)
    App_Win.IP_Label.config(text=f"  {My_IP}")
    App_Win.mainloop()