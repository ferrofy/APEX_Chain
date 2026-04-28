import sys
import os
import socket
import json
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VALIDATOR_PORT = 5001
DATA_PORT      = 5000
BANNER_W       = 62

def Clr(Code, Text): return f"\033[{Code}m{Text}\033[0m"
def Bold(T):    return Clr("1",  T)
def Green(T):   return Clr("92", T)
def Yellow(T):  return Clr("93", T)
def Red(T):     return Clr("91", T)
def Cyan(T):    return Clr("96", T)
def Dim(T):     return Clr("2",  T)
def Magenta(T): return Clr("95", T)

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
    print(f"  {Cyan(f'[{Label}]'):<36}  {Value}")

def Log(Tag, Msg, Color="dim"):
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan, "magenta": Magenta}
    print(f"  {Colors.get(Color, Dim)(f'[{Tag}]'):<28}  {Msg}")

def Get_My_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        return S.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        S.close()

def Forward_To_Data(Data_IP, Packet):
    try:
        Log("Forward", f"Connecting To Data Node @ {Cyan(Data_IP)}:{DATA_PORT}...", "cyan")
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Data_IP, DATA_PORT))
        Log("Forward", f"{Green('CONNECTED')}  ✓  Sending Decision...", "green")
        S.sendall(json.dumps(Packet).encode("utf-8"))
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
    except ConnectionRefusedError:
        return "ERROR:NO_DATA_NODE"
    except Exception as E:
        return f"ERROR:{E}"

def Handle_User(Conn, Addr, Data_IP):
    try:
        Log("Incoming", f"User Connected From {Cyan(Addr[0])}", "cyan")
        Conn.settimeout(None)
        Raw = b""
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Raw += Chunk

        if not Raw.strip():
            return

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
            else:
                Log("Data Node", Red(Result), "red")
                Conn.sendall(Result.encode("utf-8"))
        else:
            Log("Decision", f"Validator {Red('REJECTED')} → Discarded", "red")
            Conn.sendall(b"REJECTED")

    except Exception as E:
        Log("Error", str(E), "red")
    finally:
        Conn.close()

def Run_Validator_Node():
    os.system("")
    Print_Logo()

    My_IP = Get_My_IP()
    Section("This Node — Validator Node")
    Info("My IP",       Cyan(My_IP))
    Info("Listen Port", str(VALIDATOR_PORT))
    print()

    Section("Setup")
    Data_IP = input(f"  {Bold(Yellow('Enter Data Node IP'))} > ").strip()
    if not Data_IP:
        Data_IP = "127.0.0.1"
    Info("Data Node IP",   Cyan(Data_IP))
    Info("Data Node Port", str(DATA_PORT))

    print()
    Log("Ready", f"Listening For User Requests On Port {VALIDATOR_PORT}...", "green")

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", VALIDATOR_PORT))
    Srv.listen(10)

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_User, args=(Conn, Addr, Data_IP), daemon=True)
        T.start()

if __name__ == "__main__":
    Run_Validator_Node()
