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

Port       = 5000
BANNER_W   = 62
HANDSHAKE  = "Mine_RX"

Found_Devices = []
Lock          = threading.Lock()

def Clr(Code, Text):
    return f"\033[{Code}m{Text}\033[0m"

def Bold(T):    return Clr("1",  T)
def Green(T):   return Clr("92", T)
def Yellow(T):  return Clr("93", T)
def Red(T):     return Clr("91", T)
def Cyan(T):    return Clr("96", T)
def Blue(T):    return Clr("94", T)
def Dim(T):     return Clr("2",  T)

LOGO = [
    "  ███████╗███████╗██████╗ ██████╗  ██████╗ ███████╗██╗   ██╗",
    "  ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔════╝╚██╗ ██╔╝",
    "  █████╗  █████╗  ██████╔╝██████╔╝██║   ██║█████╗   ╚████╔╝ ",
    "  ██╔══╝  ██╔══╝  ██╔══██╗██╔══██╗██║   ██║██╔══╝    ╚██╔╝  ",
    "  ██║     ███████╗██║  ██║██║  ██║╚██████╔╝██║        ██║   ",
    "  ╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝        ╚═╝  ",
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
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan}
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

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256_Str(Raw)

def Load_Local_Chain(Folder):
    Chain = []
    if not os.path.exists(Folder):
        return Chain
    Files = sorted(
        [F for F in os.listdir(Folder) if F.endswith(".json")],
        key=lambda F: int(F.replace(".json", ""))
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

def Try_Connect(IP):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(0.3)
        S.connect((IP, Port))
        S.settimeout(2.0)
        try:
            Greeting = S.recv(1024).decode()
            if Greeting == HANDSHAKE:
                S.close()
                with Lock:
                    Found_Devices.append(IP)
                    Log("Node Found", f"Verified Peer → {Green(IP)}", "green")
                return
        except Exception:
            pass
        S.close()
        with Lock:
            Found_Devices.append(IP)
            Log("Node Found", f"Port-5000 Node → {Green(IP)}", "green")
    except Exception:
        pass

def Scan_Network(My_IP, Prefix):
    Section("Network Discovery Scan")
    Info("Local IP",  My_IP)
    Info("Subnet",    f"{Prefix}1  →  {Prefix}254")
    Info("Port",      str(Port))
    print()

    Threads   = []
    Done_Ref  = [0]
    Done_Lock = threading.Lock()

    def Wrapped(IP):
        Try_Connect(IP)
        with Done_Lock:
            Done_Ref[0] += 1

    for i in range(1, 255):
        IP = f"{Prefix}{i}"
        if IP in (My_IP, "127.0.0.1"):
            Done_Ref[0] += 1
            continue
        T = threading.Thread(target=Wrapped, args=(IP,), daemon=True)
        Threads.append(T)
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

def Inspect_Chain(Folder):
    Section("Local Chain Integrity Check  (Genesis → Tip)")
    Entries = Load_Local_Chain(Folder)

    if not Entries:
        Log("Chain", "No Local Blocks Found", "yellow")
        print()
        return [], []

    Corrupt = []
    Col     = f"  {'Blk':>4}  {'File':<10}  {'File-SHA256':>14}  {'Hash':>6}  {'Link':>6}  {'Status':>7}"
    print(Col)
    Sep_Parts = [Dim("─" * 4), Dim("─" * 10), Dim("─" * 14), Dim("─" * 6), Dim("─" * 6), Dim("─" * 7)]
    print("  " + "  ".join(Sep_Parts))

    for i, (Block, Path) in enumerate(Entries):
        File   = os.path.basename(Path)
        F_Hash = SHA256_File(Path)
        Recomp = Compute_Block_Hash(
            Block["Index"], Block["Timestamp"],
            Block["Data"],  Block["Previous_Hash"]
        )
        H_OK = Recomp == Block["Hash"]
        I_OK = Block["Index"] == i
        L_OK = (Block["Previous_Hash"] == "0" * 64) if i == 0 else (Block["Previous_Hash"] == Entries[i-1][0]["Hash"])

        All_OK = H_OK and L_OK and I_OK
        Flag   = Green("   OK  ") if All_OK else Red("  FAIL ")
        H_Txt  = Green("  OK") if H_OK else Red("FAIL")
        L_Txt  = Green("  OK") if L_OK else Red("FAIL")

        print(f"  {Block['Index']:>4}  {File:<10}  {F_Hash[:12]}...  {H_Txt}  {L_Txt}  {Flag}")
        if not All_OK:
            Corrupt.append(Block["Index"])

    print()
    if Corrupt:
        Log("Result", f"{Red(str(len(Corrupt)))} Corrupt Block(s) Detected At Index(es): {Corrupt}", "red")
    else:
        Log("Result", f"{Green(str(len(Entries)))} Block(s) Verified Clean  ✓", "green")
    print()

    return [B for B, _ in Entries], Corrupt

def Print_Chain_Summary(Chain):
    if not Chain:
        return
    Section("Blockchain State")
    Last = Chain[-1]
    Info("Total Blocks",    str(len(Chain)))
    Info("Chain Height",    str(Last["Index"]))
    Info("Tip Hash",        Cyan(Last["Hash"][:36] + "..."))
    Info("Tip Prev-Hash",   Dim(Last["Previous_Hash"][:36] + "..."))
    Ts = time.strftime("%Y-%m-%d  %H:%M:%S  UTC", time.gmtime(Last["Timestamp"]))
    Info("Tip Timestamp",   Ts)
    Msg = Last["Data"].get("Message", "")
    if Msg:
        Info("Tip Message", Yellow(f'"{Msg}"'))
    Node = Last["Data"].get("Node", "")
    if Node:
        Info("Mined By",    Node)
    print()

def Print_Mode(Mode, N_Peers):
    Section("Node Mode Decision")
    if Mode == "TX":
        print(f"  {Green(Bold('▶  TRANSMITTER  (TX)  —  Origin Node'))}")
        print(f"  {Dim('No existing blockchain peers found on this subnet.')}")
        print(f"  {Dim('This node will create the genesis block and accept connections.')}")
    else:
        print(f"  {Blue(Bold('▶  RECEIVER  (RX)  —  Sync Node'))}")
        print(f"  {Dim(f'{N_Peers} active peer(s) detected on this subnet.')}")
        print(f"  {Dim('This node will sync the chain, run majority recovery if needed, and receive new blocks.')}")
    print()

def Main():
    os.system("")

    Print_Logo()

    Base_Path   = os.path.dirname(os.path.abspath(__file__))
    Blocks_Path = os.path.join(Base_Path, "Blocks")
    RX_Path     = os.path.join(Base_Path, "Files", "Python", "RX.py")
    TX_Path     = os.path.join(Base_Path, "Files", "Python", "TX.py")
    Py_Exe      = sys.executable

    Section("System Information")
    My_IP, Prefix = Get_Local_Info()
    Info("Python Executable",  Py_Exe)
    Info("Node IP",            My_IP)
    Info("Blocks Directory",   Blocks_Path)
    Info("TX Script",          TX_Path)
    Info("RX Script",          RX_Path)
    print()

    Chain, Corrupt = Inspect_Chain(Blocks_Path)
    Print_Chain_Summary(Chain)

    Scan_Network(My_IP, Prefix)

    N_Peers    = len(Found_Devices)
    Node_Found = N_Peers > 0

    if Corrupt:
        Section("Chain Corruption Warning")
        print(f"  {Red(f'{len(Corrupt)} Corrupt Block(s):')}  {Corrupt}")
        if Node_Found:
            print(f"  {Yellow('Peer Recovery Will Run Automatically Via RX Majority Consensus.')}")
        else:
            print(f"  {Red('No Peers Found. Recovery Cannot Proceed Right Now.')}")
        print()

    Print_Mode("RX" if Node_Found else "TX", N_Peers)

    Section("Launching Node Process")

    if Node_Found:
        Log("Launch", f"Starting RX Node  ({N_Peers} Peer(s) Available)...", "green")
        print()
        time.sleep(0.6)
        Process = subprocess.Popen([Py_Exe, RX_Path])
    else:
        Log("Launch", "Starting TX Node  (Awaiting Peer Connections)...", "yellow")
        print()
        time.sleep(0.6)
        Process = subprocess.Popen([Py_Exe, TX_Path])

    Process.wait()

Main()