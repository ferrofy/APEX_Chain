import sys, os, socket, json, hashlib, time, threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Chain_Verify

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LISTEN_PORT = 5001
SYNC_PORT   = 5003
BANNER_W    = 60
BLOCKS_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Blocks")

def Clr(C, T): return f"\033[{C}m{T}\033[0m"
def Green(T):  return Clr("92", T)
def Yellow(T): return Clr("93", T)
def Red(T):    return Clr("91", T)
def Cyan(T):   return Clr("96", T)
def Dim(T):    return Clr("2",  T)
def Bold(T):   return Clr("1",  T)
def Magenta(T):return Clr("95", T)

def TS():
    return Dim(time.strftime("[%H:%M:%S]"))

def Log(Tag, Msg, Color=Dim):
    print(f"  {TS()} {Color(f'[{Tag}]'):<30}  {Msg}", flush=True)

def Get_My_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        return S.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        S.close()

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

def Calculate_Hash(B):
    Core = {"Block": B["Block"], "Timestamp": B["Timestamp"], "Data": B["Data"], "Prev_Hash": B["Prev_Hash"]}
    return SHA256(json.dumps(Core, sort_keys=True))

def Next_Index():
    Abs = os.path.abspath(BLOCKS_DIR)
    os.makedirs(Abs, exist_ok=True)
    return len([F for F in os.listdir(Abs) if F.startswith("block_") and F.endswith(".json")])

def Prev_Hash(Index):
    if Index == 0:
        return ""
    Path = os.path.join(os.path.abspath(BLOCKS_DIR), f"block_{Index - 1}.json")
    try:
        with open(Path) as F:
            return json.load(F).get("Hash", "")
    except:
        return ""

def Write_Block(Payload):
    Idx  = Next_Index()
    Prev = Prev_Hash(Idx)
    Ts   = int(time.time())
    B    = {"Block": Idx, "Timestamp": Ts, "Data": Payload, "Prev_Hash": Prev}
    B["Hash"] = "0" * 64 if Idx == 0 else Calculate_Hash(B)
    Path = os.path.join(os.path.abspath(BLOCKS_DIR), f"block_{Idx}.json")
    with open(Path, "w") as F:
        json.dump(B, F, indent=4)
    return Idx, B["Hash"], Path

def Handle_Validator(Conn, Addr):
    try:
        Log("VAL IN",  f"Validator Connected From {Cyan(Addr[0])}", Cyan)
        Conn.settimeout(None)
        Buf = b""
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Buf += Chunk

        if not Buf.strip():
            Log("VAL IN", "Empty Packet — Ignored", Dim)
            return

        Log("RECV",   f"{len(Buf)} Bytes Received", Cyan)
        Pkt    = json.loads(Buf.decode())
        Wallet = Pkt.get("Wallet", "unknown")
        Data   = Pkt.get("Data", {})

        Log("WALLET",  Cyan(Wallet[:16] + "...."), Cyan)
        Log("FIELDS",  str(len(Data)) + " Field(s)", Cyan)
        for K, V in Data.items():
            Log(f"  {K}", Dim(str(V)), Dim)

        Log("WRITING", f"Writing Block To Disk...", Yellow)
        Payload = {"Wallet": Wallet, **Data}
        Idx, Hash, Path = Write_Block(Payload)
        print()
        Log("BLOCK",   f"#{Idx}  →  {Green(os.path.basename(Path))}", Green)
        Log("HASH",    Cyan(Hash[:48] + "..."), Cyan)
        print()
        Conn.sendall(b"STORED")
        Log("REPLY",   Green("STORED") + " Sent To Validator", Green)

    except Exception as E:
        Log("ERROR", str(E), Red)
        try:
            Conn.sendall(b"ERROR")
        except:
            pass
    finally:
        Conn.close()
        Log("CLOSED", f"Connection With {Cyan(Addr[0])} Closed", Dim)

LOGO = [
    " ██████╗  █████╗ ████████╗ █████╗ ",
    " ██╔══██╗██╔══██╗╚══██╔══╝██╔══██╗",
    " ██║  ██║███████║   ██║   ███████║",
    " ██║  ██║██╔══██║   ██║   ██╔══██║",
    " ██████╔╝██║  ██║   ██║   ██║  ██║",
    " ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝",
]

os.system("")
print()
for L in LOGO: print(Magenta(L))
print(Magenta("  " + "─" * BANNER_W))
print(Magenta("  Data Node  —  HackIndia Spark 7  |  Start Me First!"))
print(Magenta("  " + "─" * BANNER_W))
print()

My_IP      = Get_My_IP()
Abs_Blocks = os.path.abspath(BLOCKS_DIR)
Chain_Verify.BLOCKS_DIR = Abs_Blocks

Log("MY IP",    Cyan(My_IP), Cyan)
Log("LISTENS",  f"Validator On Port {LISTEN_PORT}", Dim)
Log("BLOCKS",   Abs_Blocks, Dim)
print()

Chain, _ = Chain_Verify.Run_Verify_And_Repair(Verbose=False)
Log("CHAIN",    f"{len(Chain)} Block(s) Loaded", Cyan)

Peer_Ans = input(f"\n  {Bold(Yellow('Sync With Peer Data Node? (yes/no)'))} > ").strip().lower()
if Peer_Ans == "yes":
    Peer_IP = input(f"  {Bold(Yellow('Peer Data Node IP'))} > ").strip()
    if Peer_IP:
        Log("SYNC", f"Syncing With {Cyan(Peer_IP)}...", Yellow)
        try:
            Chain_Verify.Sync_From_Peer(Peer_IP)
            Log("SYNC", Green("Done  ✓"), Green)
        except Exception as E:
            Log("SYNC", Red(f"Failed — {E}"), Red)

Chain_Verify.Start_Sync_Server(Abs_Blocks)
Log("SYNC SRV", f"Chain Sync Server On Port {SYNC_PORT}", Cyan)

Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
Srv.bind(("0.0.0.0", LISTEN_PORT))
Srv.listen(20)

print()
Log("READY", f"{Green('Listening')} For Validator On Port {LISTEN_PORT}...", Green)
print()

while True:
    Conn, Addr = Srv.accept()
    T = threading.Thread(target=Handle_Validator, args=(Conn, Addr), daemon=True)
    T.start()
