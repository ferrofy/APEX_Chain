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

NODE_TYPE    = "DATA_NODE"
IDENTITY_PORT = 5000
DATA_PORT     = 5002
SYNC_PORT     = 5003
BANNER_W      = 62
BLOCKS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Blocks")

Peer_Registry = {
    "USER_NODE":      [],
    "VALIDATOR_NODE": [],
    "DATA_NODE":      [],
}
Registry_Lock = threading.Lock()

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
    print(Magenta("  Data Node  —  Block Storage Engine"))
    print(Magenta("  HackIndia Spark 7  |  North Region  |  Apex"))
    print(Bold(Magenta("  " + "─" * BANNER_W)))
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

def Register_Peer(Type, IP):
    with Registry_Lock:
        if IP not in Peer_Registry.get(Type, []):
            Peer_Registry.setdefault(Type, []).append(IP)
            Log("Peer Saved", f"{Yellow(Type)}  ←  {Cyan(IP)}", "cyan")

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
    Abs_Blocks = os.path.abspath(BLOCKS_DIR)
    if not os.path.exists(Abs_Blocks):
        os.makedirs(Abs_Blocks)
    Files = [F for F in os.listdir(Abs_Blocks) if F.startswith("block_") and F.endswith(".json")]
    return len(Files)

def Get_Prev_Hash(Index):
    if Index == 0:
        return ""
    Abs_Blocks = os.path.abspath(BLOCKS_DIR)
    Prev_Path  = os.path.join(Abs_Blocks, f"block_{Index - 1}.json")
    try:
        with open(Prev_Path, "r") as F:
            Prev = json.load(F)
            return Prev.get("Hash", "")
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

    if Index == 0:
        Block_Hash = "0" * 64
    else:
        Block_Hash = Calculate_Hash(Block_Data)

    Block_Data["Hash"] = Block_Hash
    Abs_Blocks = os.path.abspath(BLOCKS_DIR)
    Path       = os.path.join(Abs_Blocks, f"block_{Index}.json")

    with open(Path, "w") as F:
        json.dump(Block_Data, F, indent=4)

    return Index, Block_Hash, Path

def Handle_Identity(Conn, Addr):
    try:
        Conn.settimeout(2)
        Raw = Conn.recv(256)
        if Raw == b"WHO":
            Reply = json.dumps({
                "Type":  NODE_TYPE,
                "Ports": {"identity": IDENTITY_PORT, "data": DATA_PORT, "sync": SYNC_PORT},
            }).encode("utf-8")
            Conn.sendall(Reply)
            Peer_Type = None
        else:
            try:
                Pkt       = json.loads(Raw.decode("utf-8"))
                Peer_Type = Pkt.get("Type", "")
                Peer_IP   = Addr[0]
                if Peer_Type:
                    Register_Peer(Peer_Type, Peer_IP)
                Reply = json.dumps({"Type": NODE_TYPE}).encode("utf-8")
                Conn.sendall(Reply)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        Conn.close()

def Start_Identity_Server():
    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", IDENTITY_PORT))
    Srv.listen(20)

    def Loop():
        while True:
            try:
                Conn, Addr = Srv.accept()
                T = threading.Thread(target=Handle_Identity, args=(Conn, Addr), daemon=True)
                T.start()
            except Exception:
                break

    T = threading.Thread(target=Loop, daemon=True)
    T.start()
    return Srv

def Handle_Validator(Conn, Addr):
    try:
        Register_Peer("VALIDATOR_NODE", Addr[0])

        Raw = b""
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Raw += Chunk
        Packet = json.loads(Raw.decode("utf-8"))

        Decision = Packet.get("Decision", "").upper()
        Wallet   = Packet.get("Wallet", "unknown")
        Data     = Packet.get("Data", {})

        Section("Incoming Validator Decision")
        Info("From Validator", str(Addr))
        Info("Wallet",         Cyan(Wallet[:16] + "...."))
        Info("Decision",       Green("YES") if Decision == "YES" else Red("NO"))

        if Decision == "YES":
            Payload = {"Wallet": Wallet, **Data}
            Index, Block_Hash, Path = Write_Block(Payload)
            print()
            Log("Block Stored", f"#{Index}  →  {Green(Path)}", "green")
            Log("Hash",         Cyan(Block_Hash[:48] + "..."), "cyan")
            Conn.sendall(b"STORED")
        else:
            print()
            Log("Rejected", f"Validator Denied Request From {Yellow(Wallet[:16] + '....')}", "yellow")
            Conn.sendall(b"REJECTED")

    except Exception as E:
        Log("Error", str(E), "red")
    finally:
        Conn.close()

def Run_Data_Node():
    os.system("")
    Print_Logo()

    Abs_Blocks = os.path.abspath(BLOCKS_DIR)
    Chain_Verify.BLOCKS_DIR = Abs_Blocks

    Section("Chain Integrity Check")
    Chain, Corrupt = Chain_Verify.Run_Verify_And_Repair(Verbose=True)

    Section("Data Node Startup")
    Info("Identity Port", str(IDENTITY_PORT))
    Info("Data Port",     str(DATA_PORT))
    Info("Sync Port",     str(SYNC_PORT))
    Info("Blocks Dir",    Abs_Blocks)
    Info("Chain Height",  str(len(Chain)))
    print()

    Start_Identity_Server()
    Log("Identity", f"Handshake Server On Port {IDENTITY_PORT}", "cyan")

    Chain_Verify.Start_Sync_Server(Abs_Blocks)
    Log("Sync",     f"Chain Sync Server On Port {SYNC_PORT}", "cyan")

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", DATA_PORT))
    Srv.listen(10)

    Log("Ready", f"Waiting For Validator Decisions On Port {DATA_PORT}...", "magenta")

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_Validator, args=(Conn, Addr), daemon=True)
        T.start()

Run_Data_Node()
