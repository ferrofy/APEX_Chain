import sys
import os
import socket
import json
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "VALIDATOR_NODE"
VALIDATOR_PORT = 5001
DATA_NODE_IP   = "127.0.0.1"
DATA_PORT      = 5002
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

def Check_Data_Node_Online():
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(2)
        S.connect((DATA_NODE_IP, DATA_PORT))
        S.close()
        return True
    except Exception:
        return False

def Forward_To_Data(Packet):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((DATA_NODE_IP, DATA_PORT))
        S.sendall(json.dumps(Packet).encode("utf-8"))
        S.shutdown(socket.SHUT_WR)

        Response = b""
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

def Handle_User(Conn, Addr):
    try:
        Raw = b""
        while True:
            Chunk = Conn.recv(4096)
            if not Chunk:
                break
            Raw += Chunk

        Packet = json.loads(Raw.decode("utf-8"))
        Wallet = Packet.get("Wallet", "unknown")
        Data   = Packet.get("Data", {})

        Section("Incoming User Request — Validator Review")
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
                print(f"  {Red('Invalid Input — Type Y Or N')}")

        Forward_Packet = {
            "Wallet":   Wallet,
            "Data":     Data,
            "Decision": Decision,
        }

        print()
        if Decision == "YES":
            Log("Decision", f"Validator {Green('APPROVED')} → Forwarding To Data Node...", "green")
            Result = Forward_To_Data(Forward_Packet)
            print()
            if Result == "STORED":
                Log("Data Node", f"Block {Green('STORED')}  ✓", "green")
                Conn.sendall(b"STORED")
            elif Result == "ERROR:NO_DATA_NODE":
                Log("Data Node", f"{Red('Not Online')} — Start Data_Node.py First", "red")
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

def Run_Validator_Node():
    os.system("")
    Print_Logo()

    Section("Validator Node Startup")
    Info("Validator Port", str(VALIDATOR_PORT))
    Info("Data Node IP",   DATA_NODE_IP)
    Info("Data Node Port", str(DATA_PORT))
    Info("Role",           Yellow("The Doctor — Types YES / NO"))
    print()

    Section("Checking Data Node Connection")
    Retries = 0
    while True:
        if Check_Data_Node_Online():
            Log("Data Node", f"{Green('Online')}  ✓  Connected To {DATA_NODE_IP}:{DATA_PORT}", "green")
            break
        Retries += 1
        Log("Data Node", f"{Red('Offline')} — Retry {Retries}... (Start Data_Node.py First)", "red")
        time.sleep(3)

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", VALIDATOR_PORT))
    Srv.listen(10)

    print()
    Log("Ready", f"Waiting For User Requests On Port {VALIDATOR_PORT}...", "green")

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_User, args=(Conn, Addr), daemon=True)
        T.start()

if __name__ == "__main__":
    Run_Validator_Node()
