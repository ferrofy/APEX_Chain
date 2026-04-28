import sys
import os
import socket
import json
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "VALIDATOR_NODE"
MY_PASS        = "Doc"
DATA_NODE_IP   = "127.0.0.1"
HUB_PORT       = 5000
VALIDATOR_PORT = 5001
BANNER_W       = 62

def Clr(Code, Text):   return f"\033[{Code}m{Text}\033[0m"
def Bold(T):           return Clr("1",  T)
def Green(T):          return Clr("92", T)
def Yellow(T):         return Clr("93", T)
def Red(T):            return Clr("91", T)
def Cyan(T):           return Clr("96", T)
def Dim(T):            return Clr("2",  T)
def Magenta(T):        return Clr("95", T)

LOGO = [
    " ██╗   ██╗ █████╗ ██╗     ",
    " ██║   ██║██╔══██╗██║     ",
    " ██║   ██║███████║██║     ",
    " ╚██╗ ██╔╝██╔══██║██║     ",
    "  ╚████╔╝ ██║  ██║███████╗",
    "   ╚═══╝  ╚═╝  ╚═╝╚══════╝",
]

def Print_Logo():
    print()
    for Line in LOGO:
        print(Green(Line))
    print(Bold(Green("  " + "─" * BANNER_W)))
    print(Green("  Validator Node  —  The Doctor  (Approves / Rejects Blocks)"))
    print(Green("  HackIndia Spark 7  |  North Region  |  Apex"))
    print(Bold(Green("  " + "─" * BANNER_W)))
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

def Handshake_With_Data_Node(Data_IP):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5)
        S.connect((Data_IP, HUB_PORT))
        S.sendall(MY_PASS.encode("utf-8"))
        Reply = S.recv(16).decode("utf-8").strip()
        if Reply == "OK":
            return S
        S.close()
        return None
    except Exception:
        return None

def Connect_And_Wait_For_Data_Node(Data_IP):
    Retries = 0
    while True:
        S = Handshake_With_Data_Node(Data_IP)
        if S:
            Log("Handshake", f"{Green('OK')}  ✓  Data Node At {Data_IP}:{HUB_PORT}  Password={Yellow(MY_PASS)}", "green")
            S.close()
            return
        Retries += 1
        Log("Handshake", f"{Red('Failed')} — Retry {Retries}... (Start Data_Node.py First)", "red")
        time.sleep(3)

def Forward_To_Data(Data_IP, Packet):
    S = Handshake_With_Data_Node(Data_IP)
    if S is None:
        return "ERROR:NO_DATA_NODE"
    try:
        Payload = json.dumps(Packet).encode("utf-8")
        S.sendall(Payload)
        S.shutdown(socket.SHUT_WR)
        Response = b""
        S.settimeout(15)
        while True:
            Chunk = S.recv(4096)
            if not Chunk:
                break
            Response += Chunk
        S.close()
        return Response.decode("utf-8")
    except Exception as E:
        return f"ERROR:{E}"

def Handle_User(Conn, Addr, Data_IP):
    try:
        Conn.settimeout(5)
        Pass_In = Conn.recv(64).decode("utf-8").strip()
        if Pass_In != "User":
            Log("Auth Fail", f"Wrong User Password From {Addr[0]} → '{Pass_In}'", "red")
            Conn.sendall(b"REJECT")
            return
        Conn.sendall(b"OK")
        Log("User Auth", f"{Green('OK')}  ←  {Cyan(Addr[0])}", "cyan")

        Conn.settimeout(None)
        Raw = b""
        try:
            while True:
                Chunk = Conn.recv(4096)
                if not Chunk:
                    break
                Raw += Chunk
        except Exception:
            pass

        Packet = json.loads(Raw.decode("utf-8"))
        Wallet = Packet.get("Wallet", "unknown")
        Data   = Packet.get("Data", {})

        Section("User Request — Validator Review")
        Info("From User",      str(Addr))
        Info("Wallet Address", Cyan(Wallet[:16] + "...."))
        Info("Data Fields",    str(len(Data)))
        print()
        for K, V in Data.items():
            Info(f"  {K}", Dim(str(V)))

        print()
        print(f"  {Bold('─' * 44)}")
        print(f"  {Bold(Green('[ Y ]'))}  Accept — Write Block To Data Node")
        print(f"  {Bold(Red('[ N ]'))}   Reject — Discard Request")
        print(f"  {Bold('─' * 44)}")
        print()

        Decision = ""
        while True:
            Raw_In = input(f"  {Bold(Yellow('Validator Decision'))} > ").strip().upper()
            if Raw_In in ("Y", "YES"):
                Decision = "YES"
                break
            elif Raw_In in ("N", "NO"):
                Decision = "NO"
                break
            else:
                print(f"  {Red('Invalid — Type Y Or N')}")

        Forward_Packet = {"Wallet": Wallet, "Data": Data, "Decision": Decision}

        print()
        if Decision == "YES":
            Log("Decision", f"Validator {Green('APPROVED')} → Forwarding To Data Node...", "green")
            Result = Forward_To_Data(Data_IP, Forward_Packet)
            print()
            if Result == "STORED":
                Log("Data Node", f"Block {Green('STORED')}  ✓", "green")
                Conn.sendall(b"STORED")
            elif Result == "ERROR:NO_DATA_NODE":
                Log("Data Node", f"{Red('Not Online')}", "red")
                Conn.sendall(b"ERROR:NO_DATA_NODE")
            else:
                Log("Data Node", Dim(Result), "dim")
                Conn.sendall(Result.encode("utf-8"))
        else:
            Log("Decision", f"Validator {Red('REJECTED')} → Discarded", "red")
            Conn.sendall(b"REJECTED")

    except Exception as E:
        Log("Error", str(E), "red")
    finally:
        Conn.close()

def Run_Validator_Node(Data_IP=None):
    os.system("")
    Print_Logo()

    if not Data_IP:
        Data_IP = DATA_NODE_IP

    Section("Validator Node Startup")
    Info("My Password",   Yellow(MY_PASS))
    Info("Validator Port", str(VALIDATOR_PORT))
    Info("Data Node IP",  Data_IP)
    Info("Hub Port",      str(HUB_PORT))
    print()

    Section("Handshaking With Data Node")
    Connect_And_Wait_For_Data_Node(Data_IP)

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", VALIDATOR_PORT))
    Srv.listen(10)

    print()
    Log("Ready", f"Waiting For User Requests On Port {VALIDATOR_PORT}...", "green")

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_User, args=(Conn, Addr, Data_IP), daemon=True)
        T.start()

if __name__ == "__main__":
    Data_IP = sys.argv[1] if len(sys.argv) > 1 else DATA_NODE_IP
    Run_Validator_Node(Data_IP)
