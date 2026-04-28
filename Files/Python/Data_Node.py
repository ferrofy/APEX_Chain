import sys
import os
import socket
import json
import hashlib
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Chain_Verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE  = "DATA_NODE"
HUB_PORT   = 5000
SYNC_PORT  = 5003
BANNER_W   = 62
BLOCKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Blocks")

PASS_MAP = {
    "User":    "USER_NODE",
    "Doc":     "VALIDATOR_NODE",
    "Storage": "DATA_NODE",
}

def Clr(Code, Text):   return f"\033[{Code}m{Text}\033[0m"
def Bold(T):           return Clr("1",  T)
def Green(T):          return Clr("92", T)
def Yellow(T):         return Clr("93", T)
def Red(T):            return Clr("91", T)
def Cyan(T):           return Clr("96", T)
def Dim(T):            return Clr("2",  T)
def Magenta(T):        return Clr("95", T)

LOGO = [
    " ██████╗  █████╗ ████████╗ █████╗ ",
    " ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗",
    " ██║  ██║███████║   ██║   ███████║",
    " ██║  ██║██╔══██║   ██║   ██╔══██║",
    " ██████╔╝██║  ██║   ██║   ██║  ██║",
    " ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝",
]

def Print_Logo():
    print()
    for Line in LOGO:
        print(Magenta(Line))
    print(Bold(Magenta("  " + "─" * BANNER_W)))
    print(Magenta("  Data Node  —  Central Hub  |  Port 5000  |  Start Me First!"))
    print(Magenta("  HackIndia Spark 7  |  North Region  |  Apex"))
    print(Bold(Magenta("  " + "─" * BANNER_W)))
    print()

def Section(Title):
    print()
    print(Dim("  " + "─" * BANNER_W))
    print(f"  {Bold(Yellow(Title))}")
    print(Dim("  " + "─" * BANNER_W))

def Get_My_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        return S.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        S.close()

def Ping_Validator(Val_IP, Val_Port=5001):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(3)
        S.connect((Val_IP, Val_Port))
        S.sendall(b"PROBE")
        Reply = S.recv(16).decode("utf-8").strip()
        S.close()
        return Reply == "OK"
    except Exception:
        return False

def Info(Label, Value):
    L = Cyan(f"[{Label}]")
    print(f"  {L:<36}  {Value}")

def Log(Tag, Msg, Color="dim"):
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan, "magenta": Magenta}
    Fn = Colors.get(Color, Dim)
    print(f"  {Fn(f'[{Tag}]'):<28}  {Msg}")

def SHA256_Str(Text):
    return hashlib.sha256(Text.encode("utf-8")).hexdigest()

def Calculate_Hash(Block_Data):
    Core = {
        "Block":     Block_Data["Block"],
        "Timestamp": Block_Data["Timestamp"],
        "Data":      Block_Data["Data"],
        "Prev_Hash": Block_Data["Prev_Hash"],
    }
    return SHA256_Str(json.dumps(Core, sort_keys=True))

def Next_Block_Index():
    Abs = os.path.abspath(BLOCKS_DIR)
    if not os.path.exists(Abs):
        os.makedirs(Abs)
    Files = [F for F in os.listdir(Abs) if F.startswith("block_") and F.endswith(".json")]
    return len(Files)

def Get_Prev_Hash(Index):
    if Index == 0:
        return ""
    Abs      = os.path.abspath(BLOCKS_DIR)
    Prev_Path = os.path.join(Abs, f"block_{Index - 1}.json")
    try:
        with open(Prev_Path, "r") as F:
            return json.load(F).get("Hash", "")
    except Exception:
        return ""

def Write_Block(Payload):
    Index     = Next_Block_Index()
    Prev_Hash = Get_Prev_Hash(Index)
    Timestamp = int(time.time())
    Block_Data = {
        "Block":     Index,
        "Timestamp": Timestamp,
        "Data":      Payload,
        "Prev_Hash": Prev_Hash,
    }
    Block_Hash       = "0" * 64 if Index == 0 else Calculate_Hash(Block_Data)
    Block_Data["Hash"] = Block_Hash
    Abs  = os.path.abspath(BLOCKS_DIR)
    Path = os.path.join(Abs, f"block_{Index}.json")
    with open(Path, "w") as F:
        json.dump(Block_Data, F, indent=4)
    return Index, Block_Hash, Path

def Recv_All(Conn):
    Raw = b""
    Conn.settimeout(10)
    try:
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Raw += Chunk
    except socket.timeout:
        pass
    return Raw

def Handle_Connection(Conn, Addr):
    try:
        Conn.settimeout(5)
        Log("Handshake ◄", f"Step 1 — Incoming Connection From {Cyan(Addr[0])}", "cyan")
        Raw_Pass = Conn.recv(256).decode("utf-8").strip()
        Log("Handshake ◄", f"Step 2 — Password Received → {Yellow(Raw_Pass)}", "cyan")

        if Raw_Pass == "WHO":
            Reply = json.dumps({"Type": NODE_TYPE}).encode("utf-8")
            Conn.sendall(Reply)
            Log("Handshake ◄", f"WHO Probe — Replied With Node Type", "dim")
            return

        Node_Role = PASS_MAP.get(Raw_Pass)

        if not Node_Role:
            Log("Handshake ◄", f"Step 3 — {Red('REJECTED')}  Unknown Password", "red")
            Conn.sendall(b"REJECT")
            return

        Conn.sendall(b"OK")
        Log("Handshake ◄", f"Step 3 — {Green('ACCEPTED')}  {Yellow(Node_Role)} From {Cyan(Addr[0])}", "green")

        if Node_Role == "VALIDATOR_NODE":
            Conn.settimeout(None)
            Raw = Recv_All(Conn)
            if not Raw:
                return
            Packet   = json.loads(Raw.decode("utf-8"))
            Decision = Packet.get("Decision", "").upper()
            Wallet   = Packet.get("Wallet", "unknown")
            Data     = Packet.get("Data", {})

            Section("Validator Decision Received")
            Info("From",     f"{Cyan(Addr[0])}")
            Info("Wallet",   Cyan(Wallet[:16] + "...."))
            Info("Decision", Green("YES") if Decision == "YES" else Red("NO"))

            if Decision == "YES":
                Payload = {"Wallet": Wallet, **Data}
                Index, Block_Hash, Path = Write_Block(Payload)
                print()
                Log("Block Stored", f"#{Index}  →  {Green(Path)}", "green")
                Log("Hash",         Cyan(Block_Hash[:48] + "..."), "cyan")
                Conn.sendall(b"STORED")
            else:
                print()
                Log("Rejected", f"Block Discarded — Validator Said No", "yellow")
                Conn.sendall(b"REJECTED")

    except Exception as E:
        Log("Error", str(E), "red")
    finally:
        Conn.close()

def Run_Data_Node():
    os.system("")
    Print_Logo()

    My_IP      = Get_My_IP()
    Abs_Blocks = os.path.abspath(BLOCKS_DIR)
    Chain_Verify.BLOCKS_DIR = Abs_Blocks

    Section("This Node — Data Node")
    Info("My IP",       Cyan(My_IP))
    Info("Hub Port",    str(HUB_PORT))
    Info("Sync Port",   str(SYNC_PORT))
    Info("Passwords",   f"Validator={Green('Doc')}  Other Data={Magenta('Storage')}") 
    print()

    Section("Chain Integrity Check")
    Chain, Corrupt = Chain_Verify.Run_Verify_And_Repair(Verbose=True)
    Info("Blocks Dir",   Abs_Blocks)
    Info("Chain Height", str(len(Chain)))

    Section("Setup — Enter Validator Node IP")
    print(f"  {Dim('Validator will connect to you, but enter its IP to verify it is online.')}")
    Val_IP = input(f"  {Bold(Yellow('Validator IP'))} > ").strip()
    if not Val_IP:
        Val_IP = "127.0.0.1"
    Info("Validator IP", Cyan(Val_IP))

    Section("Setup — Peer Data Node")
    print(f"  {Dim('Connect to another Data Node for chain sync? (yes / no)')}")
    Peer_Ans = input(f"  {Bold(Yellow('Connect To Peer Data Node?'))} > ").strip().lower()

    if Peer_Ans == "yes":
        Peer_IP = input(f"  {Bold(Yellow('Other Data Node IP'))} > ").strip()
        if Peer_IP:
            Info("Peer Data IP", Cyan(Peer_IP))
            Log("Peer Sync", f"Syncing Chain With {Cyan(Peer_IP)}:{SYNC_PORT}...", "cyan")
            try:
                Chain_Verify.Sync_From_Peer(Peer_IP)
                Log("Peer Sync", f"{Green('Done')}  ✓", "green")
            except Exception as E:
                Log("Peer Sync", f"{Red('Failed')} — {E}", "red")
        else:
            Log("Peer Sync", "No IP Entered — Skipping Peer Sync.", "yellow")

    Section("Verifying Validator Is Online")
    Retries = 0
    while True:
        Log("Ping ►", f"Checking Validator @ {Cyan(Val_IP)}:5001...", "cyan")
        if Ping_Validator(Val_IP, 5001):
            Log("Ping ►", f"{Green('REACHABLE')}  ✓  Validator Is Online", "green")
            break
        Retries += 1
        Log("Ping ►", f"{Red('NOT REACHABLE')} — Retry {Retries}  (Start Validator_Node.py First)", "red")
        time.sleep(3)

    Section("Data Node Ready")
    Chain_Verify.Start_Sync_Server(Abs_Blocks)
    Log("Sync",  f"Chain Sync Server On Port {SYNC_PORT}", "cyan")

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", HUB_PORT))
    Srv.listen(20)

    Log("Ready", f"Central Hub Listening On Port {HUB_PORT}  —  Waiting For Validator...", "magenta")

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_Connection, args=(Conn, Addr), daemon=True)
        T.start()

Run_Data_Node()
