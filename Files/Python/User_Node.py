import sys
import os
import socket
import json
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "USER_NODE"
IDENTITY_PORT  = 5000
VALIDATOR_PORT = 5001
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
def Blue(T):           return Clr("94", T)

LOGO = [
    " ██╗   ██╗███████╗███████╗██████╗ ",
    " ██║   ██║██╔════╝██╔════╝██╔══██╗",
    " ██║   ██║███████╗█████╗  ██████╔╝",
    " ██║   ██║╚════██║██╔══╝  ██╔══██╗",
    " ╚██████╔╝███████║███████╗██║  ██║",
    "  ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝",
]

def Print_Logo():
    print()
    for Line in LOGO:
        print(Blue(Line))
    print(Bold(Blue("  " + "─" * BANNER_W)))
    print(Blue("  User Node  —  Data Request Sender"))
    print(Blue("  HackIndia Spark 7  |  North Region  |  Apex"))
    print(Bold(Blue("  " + "─" * BANNER_W)))
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
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan, "blue": Blue}
    Fn = Colors.get(Color, Dim)
    print(f"  {Fn(f'[{Tag}]'):<28}  {Msg}")

def Register_Peer(Type, IP):
    with Registry_Lock:
        if IP not in Peer_Registry.get(Type, []):
            Peer_Registry.setdefault(Type, []).append(IP)
            Log("Peer Saved", f"{Yellow(Type)}  ←  {Cyan(IP)}", "cyan")

def Get_Validator_IP():
    with Registry_Lock:
        Nodes = Peer_Registry.get("VALIDATOR_NODE", [])
        return Nodes[0] if Nodes else "127.0.0.1"

def Handle_Identity(Conn, Addr):
    try:
        Conn.settimeout(2)
        Raw = Conn.recv(256)
        if Raw == b"WHO":
            Reply = json.dumps({
                "Type":  NODE_TYPE,
                "Ports": {"identity": IDENTITY_PORT},
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

def Get_Wallet():
    print()
    print(f"  {Cyan('Your Wallet Address')}  (Press Enter For Default  aaaa....aaaa)")
    Wallet = input(f"  {Dim('Wallet')} > ").strip()
    if not Wallet:
        Wallet = "a" * 64
    return Wallet

def Get_Request_Data():
    Section("Data Request Builder")
    print(f"  {Dim('Enter The Data Fields You Want To Store On The Blockchain.')}")
    print(f"  {Dim('Type A Field Name And Value.  Leave Field Name Blank To Finish.')}")
    print()

    Data      = {}
    Field_Num = 1
    while True:
        Field = input(f"  {Cyan(f'Field {Field_Num} Name')}  (Or Blank To Finish) > ").strip()
        if not Field:
            break
        Value = input(f"  {Cyan(f'Field {Field_Num} Value')}                       > ").strip()
        Data[Field] = Value
        Field_Num  += 1
        print()

    return Data

def Send_To_Validator(Wallet, Data):
    Val_IP = Get_Validator_IP()
    Packet = json.dumps({"Wallet": Wallet, "Data": Data}).encode("utf-8")

    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(30)
        S.connect((Val_IP, VALIDATOR_PORT))
        S.sendall(Packet)
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
        return "ERROR:NO_VALIDATOR"
    except Exception as E:
        return f"ERROR:{E}"

def Run_User_Node(Known_Peers=None):
    os.system("")
    Print_Logo()

    Start_Identity_Server()
    Log("Identity", f"Handshake Server On Port {IDENTITY_PORT}", "cyan")

    if Known_Peers:
        Section("Announcing To Known Peers")
        for Peer_IP in Known_Peers:
            Log("Announce", f"Connecting To {Cyan(Peer_IP)}...", "cyan")
            Announce_To_Peer(Peer_IP)

    Section("User Node — Wallet Setup")
    Wallet = Get_Wallet()
    Info("Wallet Address", Cyan(Wallet[:16] + "...."))

    while True:
        Data = Get_Request_Data()

        if not Data:
            Log("Warning", "No Data Fields Entered.  Request Cancelled.", "yellow")
        else:
            Section("Sending Request To Validator")
            Val_IP = Get_Validator_IP()
            Info("Validator IP",     Cyan(Val_IP))
            Info("Wallet",           Cyan(Wallet[:16] + "...."))
            Info("Fields",           str(len(Data)))
            for K, V in Data.items():
                Info(f"  {K}", Dim(V))

            print()
            Log("Sending", f"Connecting To Validator At {Val_IP}:{VALIDATOR_PORT}...", "cyan")
            Response = Send_To_Validator(Wallet, Data)

            print()
            if Response == "STORED":
                Log("Response", f"Block {Green('STORED')} Successfully On Data Node  ✓", "green")
            elif Response == "REJECTED":
                Log("Response", f"Validator {Red('REJECTED')} → Block Not Written", "red")
            elif Response == "ERROR:NO_VALIDATOR":
                Log("Response", f"{Red('Validator Not Online')} — Start Validator_Node.py First", "red")
            else:
                Log("Response", Dim(Response), "dim")

        print()
        Again = input(f"  {Cyan('Send Another Request?')}  ({Green('y')} / {Red('n')}) > ").strip().lower()
        if Again != "y":
            break

    print()
    Log("User Node", "Session Ended.  Goodbye.", "cyan")
    print()

if __name__ == "__main__":
    Known = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    Run_User_Node(Known)
