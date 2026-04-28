import subprocess
import sys
import os
import socket
import threading
import time
import json
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

IDENTITY_PORT = 5000
BANNER_W      = 62
SCAN_TIMEOUT  = 0.35
SCAN_WORKERS  = 80

def Clr(Code, Text):
    return f"\033[{Code}m{Text}\033[0m"

def Bold(T):    return Clr("1",  T)
def Green(T):   return Clr("92", T)
def Yellow(T):  return Clr("93", T)
def Red(T):     return Clr("91", T)
def Cyan(T):    return Clr("96", T)
def Blue(T):    return Clr("94", T)
def Dim(T):     return Clr("2",  T)
def Magenta(T): return Clr("95", T)

LOGO = [
    " █████╗ ██████╗ ███████╗██╗  ██╗",
    "██╔══██╗██╔══██╗██╔════╝╚██╗██╔╝",
    "███████║██████╔╝█████╗   ╚███╔╝ ",
    "██╔══██║██╔═══╝ ██╔══╝   ██╔██╗ ",
    "██║  ██║██║     ███████╗██╔╝ ██╗",
    "╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝"
]

def Print_Logo():
    print()
    for Line in LOGO:
        print(Cyan(Line))
    print(Bold(Cyan("  " + "─" * BANNER_W)))
    print(Cyan("  Distributed Blockchain Node Network — Terminal Edition"))
    print(Cyan("  HackIndia Spark 7  |  North Region  |  Apex"))
    print(Bold(Cyan("  " + "─" * BANNER_W)))
    print()

def Section(Title):
    print()
    print(Dim("  " + "─" * BANNER_W))
    print(f"  {Bold(Yellow(Title))}")
    print(Dim("  " + "─" * BANNER_W))

def Info(Label, Value):
    L = Cyan(f"[{Label}]")
    print(f"  {L:<36}  {Value}")

def Log(Tag, Msg, Color="dim"):
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan, "magenta": Magenta}
    Fn = Colors.get(Color, Dim)
    print(f"  {Fn(f'[{Tag}]'):<28}  {Msg}")

def Get_Local_Info():
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

def SHA256_File(Path):
    with open(Path, "rb") as F:
        return hashlib.sha256(F.read()).hexdigest()

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

def Load_Local_Chain(Folder):
    Chain = []
    if not os.path.exists(Folder):
        return Chain
    Files = sorted(
        [F for F in os.listdir(Folder) if F.startswith("block_") and F.endswith(".json")],
        key=lambda F: int(F.replace("block_", "").replace(".json", ""))
    )
    for File in Files:
        Path = os.path.join(Folder, File)
        try:
            with open(Path, "r") as F:
                Block = json.load(F)
                Chain.append((Block, Path))
        except Exception:
            pass
    return Chain

def Probe_Node(IP, Found, Lock):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(SCAN_TIMEOUT)
        S.connect((IP, IDENTITY_PORT))
        S.settimeout(1.5)
        S.sendall(b"WHO")
        Raw = b""
        try:
            while True:
                Chunk = S.recv(512)
                if not Chunk:
                    break
                Raw += Chunk
        except socket.timeout:
            pass
        S.close()

        if Raw:
            Info_Map = json.loads(Raw.decode("utf-8"))
            Node_Type = Info_Map.get("Type", "UNKNOWN")
            with Lock:
                Found.append({"IP": IP, "Type": Node_Type, "Info": Info_Map})
    except Exception:
        pass

def Scan_Network(My_IP, Prefix):
    Section("Network Discovery  —  Scanning For Active Nodes")
    Info("Local IP", My_IP)
    Info("Subnet",   f"{Prefix}1  →  {Prefix}254")
    Info("Port",     str(IDENTITY_PORT))
    print()

    Found     = []
    Lock      = threading.Lock()
    Threads   = []
    Done_Ref  = [0]
    Done_Lock = threading.Lock()

    def Wrapped(IP):
        Probe_Node(IP, Found, Lock)
        with Done_Lock:
            Done_Ref[0] += 1

    for i in range(1, 255):
        IP = f"{Prefix}{i}"
        if IP == My_IP:
            Done_Ref[0] += 1
            continue
        T = threading.Thread(target=Wrapped, args=(IP,), daemon=True)
        Threads.append(T)

    for k in range(0, len(Threads), SCAN_WORKERS):
        for T in Threads[k : k + SCAN_WORKERS]:
            T.start()

    Total = 253
    while Done_Ref[0] < Total:
        Pct    = Done_Ref[0] / Total
        Filled = int(Pct * 44)
        Bar    = "█" * Filled + "░" * (44 - Filled)
        print(f"\r  {Cyan(Bar)}  {int(Pct*100):>3}%", end="", flush=True)
        time.sleep(0.04)

    for T in Threads:
        T.join()

    print(f"\r  {Cyan('█' * 44)}  100%", flush=True)
    print()
    return Found

def Print_Discovered_Nodes(Nodes):
    Section("Discovered Nodes On Network")
    if not Nodes:
        Log("Scan", "No Active Nodes Found On This Subnet.", "yellow")
        print()
        return

    Type_Colors = {
        "USER_NODE":      Blue,
        "VALIDATOR_NODE": Green,
        "DATA_NODE":      Magenta,
        "UNKNOWN":        Dim,
    }

    for N in Nodes:
        N_Type = N["Type"]
        Color  = Type_Colors.get(N_Type, Dim)
        print(f"  {Color(f'[{N_Type}]'):<38}  {Cyan(N['IP'])}")
    print()

def Print_Chain_Summary(Folder):
    Chain_Entries = Load_Local_Chain(Folder)
    if not Chain_Entries:
        return
    Section("Local Blockchain State")
    Last = Chain_Entries[-1][0]
    Info("Total Blocks",  str(len(Chain_Entries)))
    Info("Chain Height",  str(Last["Block"]))
    Ts = Last.get("Timestamp", "")
    if isinstance(Ts, int):
        Info("Tip Timestamp", f"{Ts}  ({time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(Ts))})")
    else:
        Info("Tip Timestamp", str(Ts))
    Wallet = Last["Data"].get("Wallet", "")
    if Wallet:
        Info("Last Wallet",  Cyan(Wallet[:16] + "...."))
    print()

def Print_Architecture():
    Section("3-Node Architecture")
    print(f"  {Blue('User Node')}    {Dim('─────►')}  {Green('Validator Node')}  {Dim('─────►')}  {Magenta('Data Node')}")
    print()
    print(f"  {Magenta('Port 5000')}  Central Hub  (Data Node)  —  All Nodes Handshake Here")
    print(f"  {Green('Port 5001')}  User → Validator")
    print(f"  {Cyan('Port 5003')}  Chain Peer Sync  (Data Nodes)")
    print()
    print(f"  {Yellow('Passwords')}  User={Blue('User')}   Validator={Green('Doc')}   Data={Magenta('Storage')}")
    print()

def Print_Node_Menu():
    Section("Which Node Are You?")
    print(f"  {Magenta('[ 3 ]')}  {Magenta('Data Node')}       — Central Hub  (Start First!)  Port 5000 + 5003")
    print(f"  {Green('[ 2 ]')}  {Green('Validator Node')} — Approve / Reject              Port 5001")
    print(f"  {Blue('[ 1 ]')}  {Blue('User Node')}       — Send Data Requests            Port 5001")
    print(f"  {Dim('[ 0 ]')}  {Dim('Exit')}")
    print()

def Main():
    os.system("")

    Print_Logo()

    Base_Path   = os.path.dirname(os.path.abspath(__file__))
    Blocks_Path = os.path.join(Base_Path, "Blocks")
    User_Path   = os.path.join(Base_Path, "Files", "Python", "User_Node.py")
    Val_Path    = os.path.join(Base_Path, "Files", "Python", "Validator_Node.py")
    Data_Path   = os.path.join(Base_Path, "Files", "Python", "Data_Node.py")
    Py_Exe      = sys.executable

    Section("System Information")
    My_IP, Prefix = Get_Local_Info()
    Info("Python Executable", Py_Exe)
    Info("Node IP",           My_IP)
    Info("Blocks Directory",  Blocks_Path)
    print()

    Print_Chain_Summary(Blocks_Path)
    Print_Architecture()

    Nodes = Scan_Network(My_IP, Prefix)
    Print_Discovered_Nodes(Nodes)

    By_Type = {}
    for N in Nodes:
        By_Type.setdefault(N["Type"], []).append(N["IP"])

    if Nodes:
        Section("Peer Registry")
        for T, IPs in By_Type.items():
            Info(T, "  ".join([Cyan(IP) for IP in IPs]))
        print()

    Data_IPs = By_Type.get("DATA_NODE", [])
    Val_IPs  = By_Type.get("VALIDATOR_NODE", [])

    Data_IP = Data_IPs[0] if Data_IPs else "127.0.0.1"
    Val_IP  = Val_IPs[0]  if Val_IPs  else "127.0.0.1"

    Print_Node_Menu()
    Choice = input(f"  {Bold(Yellow('Select Node Type'))} > ").strip()

    Scripts = {
        "1": ("User Node",      User_Path),
        "2": ("Validator Node", Val_Path),
        "3": ("Data Node",      Data_Path),
    }

    if Choice in Scripts:
        Name, Script = Scripts[Choice]
        Section(f"Launching {Name}")
        Log("Launch", f"Starting {Yellow(Name)}...", "green")
        print()
        time.sleep(0.3)

        if Choice == "1":
            Info("Validator IP", Cyan(Val_IP))
            Process = subprocess.Popen([Py_Exe, Script, Val_IP])
        elif Choice == "2":
            Info("Data Node IP", Cyan(Data_IP))
            Process = subprocess.Popen([Py_Exe, Script, Data_IP])
        else:
            Process = subprocess.Popen([Py_Exe, Script])
        Process.wait()

    elif Choice == "0":
        Log("Exit", "Goodbye.", "cyan")
        print()
    else:
        Log("Error", "Invalid Choice.  Restart And Try Again.", "red")
        print()

Main()