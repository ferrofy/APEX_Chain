import sys, os, socket, json, time, threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

USER_PORT = 5000
DATA_PORT = 5000
BANNER_W  = 60

def Clr(C, T): return f"\033[{C}m{T}\033[0m"
def Green(T):  return Clr("92", T)
def Yellow(T): return Clr("93", T)
def Red(T):    return Clr("91", T)
def Cyan(T):   return Clr("96", T)
def Dim(T):    return Clr("2",  T)
def Bold(T):   return Clr("1",  T)
def TS():      return Dim(time.strftime("[%H:%M:%S]"))
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

def Connect_Back_To_User(User_IP, Callback_Port):
    try:
        Log("CALLBACK", f"Connecting Back To User @ {Cyan(User_IP)}:{Callback_Port}...", Cyan)
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((User_IP, Callback_Port))
        S.sendall(b"HELLO")
        Reply = S.recv(16).decode().strip()
        S.close()
        if Reply == "ACK":
            Log("CALLBACK", f"{Green('Two-Way Connection Confirmed')}  ✓", Green)
            return True
        Log("CALLBACK", f"{Red('No ACK From User')}", Red)
        return False
    except Exception as E:
        Log("CALLBACK", f"{Red('Failed')} — {E}", Red)
        return False

def Forward_To_Data(Data_IP, Wallet, Data):
    try:
        Log("DATA", f"Connecting To Data Node @ {Cyan(Data_IP)}:{DATA_PORT}...", Cyan)
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Data_IP, DATA_PORT))
        Log("DATA", f"{Green('Connected')}  ✓  Sending Block...", Green)
        Pkt = json.dumps({"Wallet": Wallet, "Data": Data}).encode()
        S.sendall(Pkt)
        S.shutdown(socket.SHUT_WR)
        S.settimeout(15)
        Buf = b""
        while True:
            Chunk = S.recv(4096)
            if not Chunk:
                break
            Buf += Chunk
        S.close()
        return Buf.decode()
    except ConnectionRefusedError:
        return "ERROR:DATA_OFFLINE"
    except Exception as E:
        return f"ERROR:{E}"

def Handle_User(Conn, Addr, Data_IP):
    try:
        Log("USER IN", f"User Connected From {Cyan(Addr[0])}", Cyan)
        Conn.settimeout(None)
        Buf = b""
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Buf += Chunk

        if not Buf.strip():
            Log("USER IN", "Empty Packet — Ignored", Dim)
            return

        Log("RECV",   f"{len(Buf)} Bytes Received", Cyan)
        Pkt           = json.loads(Buf.decode())
        Wallet        = Pkt.get("Wallet", "unknown")
        Data          = Pkt.get("Data", {})
        User_IP       = Pkt.get("User_IP", Addr[0])
        Callback_Port = Pkt.get("Callback_Port", 5002)

        print()
        print(f"  {'─' * BANNER_W}")
        print(f"  {Bold(Yellow('NEW REQUEST FROM USER'))}")
        print(f"  {'─' * BANNER_W}")
        Log("FROM",   Cyan(Addr[0]), Cyan)
        Log("WALLET", Cyan(Wallet[:16] + "...."), Cyan)
        for K, V in Data.items():
            Log(f"  {K}", Dim(str(V)), Dim)
        print()

        Log("STEP 1", "Connecting Back To User To Confirm Connection...", Yellow)
        Callback_OK = Connect_Back_To_User(User_IP, Callback_Port)

        if not Callback_OK:
            Log("STEP 1", f"{Red('Callback Failed')} — Cannot Verify User Connection", Red)
            Conn.sendall(b"ERROR:CALLBACK_FAILED")
            return

        Log("STEP 1", f"{Green('Connection Verified Both Ways')}  ✓", Green)
        print()

        print(f"  {Bold(Green('[ Y ]'))}  Approve — Write Block To Data Node")
        print(f"  {Bold(Red('[ N ]'))}  Reject  — Discard")
        print()

        Decision = ""
        while True:
            Inp = input(f"  {Bold(Yellow('Decision'))} > ").strip().upper()
            if Inp in ("Y", "YES"):
                Decision = "YES"
                break
            elif Inp in ("N", "NO"):
                Decision = "NO"
                break
            else:
                print(f"  {Red('Type Y or N')}")

        print()
        Log("DECISION", Green("APPROVED") if Decision == "YES" else Red("REJECTED"),
            Green if Decision == "YES" else Red)

        if Decision == "YES":
            Log("STEP 2", f"Connecting To Data Node @ {Cyan(Data_IP)}...", Yellow)
            Result = Forward_To_Data(Data_IP, Wallet, Data)
            if Result == "STORED":
                Log("STEP 2", f"Block {Green('STORED')}  ✓", Green)
                Conn.sendall(b"STORED")
            else:
                Log("STEP 2", Red(Result), Red)
                Conn.sendall(Result.encode())
        else:
            Conn.sendall(b"REJECTED")

    except Exception as E:
        Log("ERROR", str(E), Red)
    finally:
        Conn.close()
        Log("CLOSED", f"Connection With {Cyan(Addr[0])} Closed", Dim)

LOGO = [
    " ██╗   ██╗ █████╗ ██╗     ",
    " ██║   ██║██╔══██╗██║     ",
    " ██║   ██║███████║██║     ",
    " ╚██╗ ██╔╝██╔══██║██║     ",
    "  ╚████╔╝ ██║  ██║███████╗",
    "   ╚═══╝  ╚═╝  ╚═╝╚══════╝",
]

os.system("")
print()
for L in LOGO: print(Clr("92", L))
print(Green("  " + "─" * BANNER_W))
print(Green("  Validator Node  —  HackIndia Spark 7"))
print(Green("  " + "─" * BANNER_W))
print()

My_IP = Get_My_IP()
Log("MY IP",    Cyan(My_IP), Cyan)
Log("LISTENS",  f"Users On Port {USER_PORT}", Dim)
Log("FORWARDS", f"Data On Port  {DATA_PORT} (Data Node Machine)", Dim)
print()

Data_IP = input(f"  {Bold(Yellow('Enter Data Node IP'))} > ").strip() or "127.0.0.1"
Log("DATA NODE", Cyan(Data_IP), Cyan)
print()

Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
Srv.bind(("0.0.0.0", USER_PORT))
Srv.listen(10)

Log("READY", f"{Green('Listening')} For Users On Port {USER_PORT}...", Green)
print()

while True:
    Conn, Addr = Srv.accept()
    T = threading.Thread(target=Handle_User, args=(Conn, Addr, Data_IP), daemon=True)
    T.start()
