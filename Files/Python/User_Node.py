import sys, os, socket, json, time, threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LISTEN_PORT = 5000
BANNER_W    = 60

def Clr(C, T): return f"\033[{C}m{T}\033[0m"
def Green(T):  return Clr("92", T)
def Yellow(T): return Clr("93", T)
def Red(T):    return Clr("91", T)
def Cyan(T):   return Clr("96", T)
def Dim(T):    return Clr("2",  T)
def Bold(T):   return Clr("1",  T)
def Blue(T):   return Clr("94", T)

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

def Get_Wallet():
    print()
    print(f"  {Cyan('Wallet Address')}  (Enter Or Press Return For Default)")
    W = input(f"  {Dim('>')} ").strip()
    return W if W else "a" * 64

def Get_Fields():
    print(f"\n  {Cyan('Enter Data Fields')}  {Dim('(Blank Name To Finish)')}\n")
    Data, N = {}, 1
    while True:
        K = input(f"  {Cyan(f'Field {N}')} Name  > ").strip()
        if not K:
            break
        V = input(f"  {Cyan(f'Field {N}')} Value > ").strip()
        Data[K] = V
        N += 1
        print()
    return Data

def Send_To_Validator(Val_IP, Wallet, Data):
    try:
        Log("CONNECT", f"Connecting To Validator  {Cyan(Val_IP)}:{LISTEN_PORT}", Cyan)
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Val_IP, LISTEN_PORT))
        Log("CONNECT", f"{Green('Connected')}  ✓", Green)

        Pkt = json.dumps({"Wallet": Wallet, "Data": Data}).encode()
        S.sendall(Pkt)
        S.shutdown(socket.SHUT_WR)
        Log("SEND",    f"Data Sent  ({len(Pkt)} bytes)", Cyan)

        Log("WAIT",    "Waiting For Validator Decision...", Yellow)
        S.settimeout(None)
        Buf = b""
        while True:
            Chunk = S.recv(4096)
            if not Chunk:
                break
            Buf += Chunk
        S.close()
        return Buf.decode()
    except ConnectionRefusedError:
        return "ERROR:VALIDATOR_OFFLINE"
    except Exception as E:
        return f"ERROR:{E}"

LOGO = [
    " ██╗   ██╗███████╗███████╗██████╗ ",
    " ██║   ██║██╔════╝██╔════╝██╔══██╗",
    " ██║   ██║███████╗█████╗  ██████╔╝",
    " ██║   ██║╚════██║██╔══╝  ██╔══██╗",
    " ╚██████╔╝███████║███████╗██║  ██║",
    "  ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝",
]

os.system("")
print()
for L in LOGO: print(Blue(L))
print(Blue("  " + "─" * BANNER_W))
print(Blue("  User Node  —  HackIndia Spark 7"))
print(Blue("  " + "─" * BANNER_W))
print()

My_IP = Get_My_IP()
Log("MY IP",    Cyan(My_IP), Cyan)
Log("CONNECTS", f"Validator On Port {LISTEN_PORT}", Dim)
print()

Val_IP = input(f"  {Bold(Yellow('Enter Validator IP'))} > ").strip() or "127.0.0.1"
Log("VALIDATOR", Cyan(Val_IP), Cyan)

Wallet = Get_Wallet()
Log("WALLET", Cyan(Wallet[:16] + "...."), Cyan)

while True:
    Data = Get_Fields()
    if not Data:
        Log("WARN", "No Fields Entered — Cancelled.", Yellow)
    else:
        Log("INFO", f"{len(Data)} Field(s) Ready To Send", Cyan)
        Resp = Send_To_Validator(Val_IP, Wallet, Data)
        print()
        if Resp == "STORED":
            Log("RESULT", f"Block {Green('STORED')} Successfully  ✓", Green)
        elif Resp == "REJECTED":
            Log("RESULT", f"Validator {Red('REJECTED')} — Block Not Written", Red)
        else:
            Log("RESULT", Red(Resp), Red)

    print()
    if input(f"  {Cyan('Send Another?')}  (y / n) > ").strip().lower() != "y":
        break

print()
Log("EXIT", "User Node Closed.", Dim)
print()
