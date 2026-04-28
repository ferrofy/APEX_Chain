import sys
import os
import socket
import json
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "VALIDATOR_NODE"
IDENTITY_PORT  = 5000
VALIDATOR_PORT = 5001
DATA_NODE_IP   = "127.0.0.1"
DATA_PORT      = 5002
BANNER_W       = 62

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

def Register_Peer(Type, IP):
    with Registry_Lock:
        if IP not in Peer_Registry.get(Type, []):
            Peer_Registry.setdefault(Type, []).append(IP)
            Log("Peer Saved", f"{Yellow(Type)}  ←  {Cyan(IP)}", "cyan")

def Get_Data_Node_IP():
    with Registry_Lock:
        Nodes = Peer_Registry.get("DATA_NODE", [])
        return Nodes[0] if Nodes else DATA_NODE_IP

def Handle_Identity(Conn, Addr):
    try:
        Conn.settimeout(2)
        Raw = Conn.recv(256)
        if Raw == b"WHO":
            Reply = json.dumps({
                "Type":  NODE_TYPE,
                "Ports": {"identity": IDENTITY_PORT, "validator": VALIDATOR_PORT},
            }).encode("utf-8")
            Conn.sendall(Reply)
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

def Announce_To_Peer(Peer_IP):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(2)
        S.connect((Peer_IP, IDENTITY_PORT))
        S.sendall(json.dumps({"Type": NODE_TYPE}).encode("utf-8"))
        Raw = S.recv(512)
        S.close()
        Resp      = json.loads(Raw.decode("utf-8"))
        Peer_Type = Resp.get("Type", "")
        if Peer_Type:
            Register_Peer(Peer_Type, Peer_IP)
    except Exception:
        pass

def Forward_To_Data(Packet):
    Data_IP = Get_Data_Node_IP()
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Data_IP, DATA_PORT))
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
        Register_Peer("USER_NODE", Addr[0])

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

def Run_Validator_Node(Known_Peers=None):
    os.system("")
    Print_Logo()
    Section("Validator Node Startup")
    Info("Identity Port",  str(IDENTITY_PORT))
    Info("Validator Port", str(VALIDATOR_PORT))
    Info("Data Port",      str(DATA_PORT))
    Info("Role",           Yellow("The Doctor — Types YES / NO"))
    print()

    Start_Identity_Server()
    Log("Identity", f"Handshake Server On Port {IDENTITY_PORT}", "cyan")

    if Known_Peers:
        Section("Announcing To Known Peers")
        for Peer_IP in Known_Peers:
            Log("Announce", f"Connecting To {Cyan(Peer_IP)}...", "cyan")
            Announce_To_Peer(Peer_IP)

    Srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Srv.bind(("0.0.0.0", VALIDATOR_PORT))
    Srv.listen(10)

    Log("Ready", f"Waiting For User Requests On Port {VALIDATOR_PORT}...", "green")

    while True:
        Conn, Addr = Srv.accept()
        T = threading.Thread(target=Handle_User, args=(Conn, Addr), daemon=True)
        T.start()

if __name__ == "__main__":
    Known = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    Run_Validator_Node(Known)
