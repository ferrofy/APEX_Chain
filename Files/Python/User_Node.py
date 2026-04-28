import sys, os, socket, json, time, threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VAL_PORT      = 5000
CALLBACK_PORT = 5002
BANNER_W      = 60

def Clr(C, T): return f"\033[{C}m{T}\033[0m"
def Green(T):  return Clr("92", T)
def Yellow(T): return Clr("93", T)
def Red(T):    return Clr("91", T)
def Cyan(T):   return Clr("96", T)
def Dim(T):    return Clr("2",  T)
def Bold(T):   return Clr("1",  T)
def Blue(T):   return Clr("94", T)
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

Callback_Event  = threading.Event()
Callback_Status = {"ok": False}

def Start_Callback_Listener():
    def Listen():
        Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        Srv.bind(("0.0.0.0", CALLBACK_PORT))
        Srv.listen(5)
        Log("CALLBACK", f"Waiting For Validator Callback On Port {CALLBACK_PORT}...", Yellow)
        try:
            Srv.settimeout(30)
            Conn, Addr = Srv.accept()
            Msg = Conn.recv(64).decode().strip()
            Conn.sendall(b"ACK")
            Conn.close()
            Srv.close()
            if Msg == "HELLO":
                Callback_Status["ok"] = True
                Log("CALLBACK", f"{Green('Validator Connected Back')}  ✓  From {Cyan(Addr[0])}", Green)
            else:
                Log("CALLBACK", f"{Red('Unexpected Message')} — {Msg}", Red)
        except socket.timeout:
            Log("CALLBACK", f"{Red('Timeout')} — Validator Did Not Connect Back In 30s", Red)
        finally:
            Callback_Event.set()
    T = threading.Thread(target=Listen, daemon=True)
    T.start()

def Send_To_Validator(Val_IP, My_IP, Wallet, Data):
    try:
        Log("CONNECT", f"Connecting To Validator @ {Cyan(Val_IP)}:{VAL_PORT}...", Cyan)
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Val_IP, VAL_PORT))
        Log("CONNECT", f"{Green('Connected')}  ✓", Green)

        Pkt = json.dumps({
            "Wallet":        Wallet,
            "Data":          Data,
            "User_IP":       My_IP,
            "Callback_Port": CALLBACK_PORT
        }).encode()
        S.sendall(Pkt)
        S.shutdown(socket.SHUT_WR)
        Log("SEND",    f"Packet Sent  ({len(Pkt)} Bytes)", Cyan)
        Log("WAIT",    "Waiting For Validator Callback + Decision...", Yellow)

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
Log("MY IP",        Cyan(My_IP), Cyan)
Log("SENDS TO",     f"Validator Port {VAL_PORT}", Dim)
Log("CALLBACK ON",  f"My Port {CALLBACK_PORT}  (Validator Calls Back Here)", Dim)
print()

Val_IP = input(f"  {Bold(Yellow('Enter Validator IP'))} > ").strip() or "127.0.0.1"
Log("VALIDATOR", Cyan(Val_IP), Cyan)
print()

print(f"  {Cyan('Wallet Address')}  (Press Enter For Default  aaaa....aaaa)")
Wallet = input(f"  {Dim('>')} ").strip() or ("a" * 64)
Log("WALLET", Cyan(Wallet[:16] + "...."), Cyan)

while True:
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

    if not Data:
        Log("WARN", "No Fields — Cancelled", Yellow)
    else:
        Callback_Event.clear()
        Callback_Status["ok"] = False
        Start_Callback_Listener()

        Resp = Send_To_Validator(Val_IP, My_IP, Wallet, Data)

        Callback_Event.wait(timeout=35)

        print()
        if not Callback_Status["ok"]:
            Log("WARN", Yellow("Validator Did Not Connect Back — Connection Unverified"), Yellow)

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
