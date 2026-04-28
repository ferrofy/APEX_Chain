import sys
import os
import socket
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VALIDATOR_PORT = 5001
BANNER_W       = 62

def Clr(Code, Text): return f"\033[{Code}m{Text}\033[0m"
def Bold(T):  return Clr("1",  T)
def Green(T): return Clr("92", T)
def Yellow(T):return Clr("93", T)
def Red(T):   return Clr("91", T)
def Cyan(T):  return Clr("96", T)
def Dim(T):   return Clr("2",  T)
def Blue(T):  return Clr("94", T)

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
    print(f"  {Cyan(f'[{Label}]'):<36}  {Value}")

def Log(Tag, Msg, Color="dim"):
    Colors = {"green": Green, "red": Red, "yellow": Yellow, "dim": Dim, "cyan": Cyan, "blue": Blue}
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

def Send_To_Validator(Val_IP, Wallet, Data):
    try:
        Log("Connect", f"Connecting To Validator @ {Cyan(Val_IP)}:{VALIDATOR_PORT}...", "cyan")
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(10)
        S.connect((Val_IP, VALIDATOR_PORT))
        Log("Connect", f"{Green('CONNECTED')}  ✓", "green")

        Packet = json.dumps({"Wallet": Wallet, "Data": Data}).encode("utf-8")
        S.sendall(Packet)
        S.shutdown(socket.SHUT_WR)

        Log("Waiting", "Waiting For Validator Decision...", "yellow")
        S.settimeout(None)
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

def Get_Wallet():
    print()
    print(f"  {Cyan('Your Wallet Address')}  (Press Enter For Default  aaaa....aaaa)")
    Wallet = input(f"  {Dim('Wallet')} > ").strip()
    return Wallet if Wallet else "a" * 64

def Get_Request_Data():
    Section("Data Request Builder")
    print(f"  {Dim('Enter Fields To Store. Leave Name Blank To Finish.')}")
    print()
    Data = {}
    N = 1
    while True:
        Field = input(f"  {Cyan(f'Field {N} Name')}  (Blank To Finish) > ").strip()
        if not Field:
            break
        Value = input(f"  {Cyan(f'Field {N} Value')}                    > ").strip()
        Data[Field] = Value
        N += 1
        print()
    return Data

def Run_User_Node():
    os.system("")
    Print_Logo()

    My_IP = Get_My_IP()
    Section("This Node — User Node")
    Info("My IP", Cyan(My_IP))
    print()

    Section("Setup")
    Val_IP = input(f"  {Bold(Yellow('Enter Validator IP'))} > ").strip()
    if not Val_IP:
        Val_IP = "127.0.0.1"
    Info("Validator IP",   Cyan(Val_IP))
    Info("Validator Port", str(VALIDATOR_PORT))

    Section("Wallet Setup")
    Wallet = Get_Wallet()
    Info("Wallet", Cyan(Wallet[:16] + "...."))

    while True:
        Data = Get_Request_Data()
        if not Data:
            Log("Warning", "No Fields Entered — Request Cancelled.", "yellow")
        else:
            Section("Sending Request To Validator")
            for K, V in Data.items():
                Info(f"  {K}", Dim(V))
            print()
            Response = Send_To_Validator(Val_IP, Wallet, Data)
            print()
            if Response == "STORED":
                Log("Response", f"Block {Green('STORED')} Successfully  ✓", "green")
            elif Response == "REJECTED":
                Log("Response", f"Validator {Red('REJECTED')} → Block Not Written", "red")
            elif "ERROR" in Response:
                Log("Response", Red(Response), "red")
            else:
                Log("Response", Dim(Response), "dim")

        print()
        Again = input(f"  {Cyan('Send Another Request?')}  ({Green('y')} / {Red('n')}) > ").strip().lower()
        if Again != "y":
            break

    print()
    Log("User Node", "Session Ended. Goodbye.", "cyan")
    print()

if __name__ == "__main__":
    Run_User_Node()
