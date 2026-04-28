import sys
import os
import socket
import json
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "USER_NODE"
MY_PASS        = "User"
VALIDATOR_IP   = "127.0.0.1"
VALIDATOR_PORT = 5001
BANNER_W       = 62

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

def Check_Validator(Val_IP):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(3)
        S.connect((Val_IP, VALIDATOR_PORT))
        S.sendall(MY_PASS.encode("utf-8"))
        Reply = S.recv(16).decode("utf-8").strip()
        S.close()
        return Reply == "OK"
    except Exception:
        return False

def Wait_For_Validator(Val_IP):
    Retries = 0
    while True:
        if Check_Validator(Val_IP):
            Log("Handshake", f"{Green('OK')}  ✓  Validator At {Val_IP}:{VALIDATOR_PORT}  Password={Yellow(MY_PASS)}", "green")
            return
        Retries += 1
        Log("Handshake", f"{Red('Failed')} — Retry {Retries}... (Start Validator_Node.py First)", "red")
        time.sleep(3)

def Send_To_Validator(Val_IP, Wallet, Data):
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5)
        S.connect((Val_IP, VALIDATOR_PORT))
        S.sendall(MY_PASS.encode("utf-8"))
        Reply = S.recv(16).decode("utf-8").strip()
        if Reply != "OK":
            S.close()
            return "ERROR:AUTH_REJECTED"

        Packet = json.dumps({"Wallet": Wallet, "Data": Data}).encode("utf-8")
        S.settimeout(60)
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

def Run_User_Node(Val_IP=None):
    os.system("")
    Print_Logo()

    if not Val_IP:
        Val_IP = VALIDATOR_IP

    Section("User Node Startup")
    Info("My Password",    Yellow(MY_PASS))
    Info("Validator IP",   Val_IP)
    Info("Validator Port", str(VALIDATOR_PORT))
    print()

    Section("Handshaking With Validator Node")
    Wait_For_Validator(Val_IP)

    Section("Wallet Setup")
    Wallet = Get_Wallet()
    Info("Wallet Address", Cyan(Wallet[:16] + "...."))

    while True:
        Data = Get_Request_Data()

        if not Data:
            Log("Warning", "No Data Fields Entered.  Request Cancelled.", "yellow")
        else:
            Section("Sending Request To Validator")
            Info("Validator",  f"{Cyan(Val_IP)}:{VALIDATOR_PORT}")
            Info("Wallet",     Cyan(Wallet[:16] + "...."))
            Info("Fields",     str(len(Data)))
            for K, V in Data.items():
                Info(f"  {K}", Dim(V))

            print()
            Log("Sending", f"Connecting To Validator At {Val_IP}:{VALIDATOR_PORT}...", "cyan")
            Response = Send_To_Validator(Val_IP, Wallet, Data)

            print()
            if Response == "STORED":
                Log("Response", f"Block {Green('STORED')} Successfully On Data Node  ✓", "green")
            elif Response == "REJECTED":
                Log("Response", f"Validator {Red('REJECTED')} → Block Not Written", "red")
            elif Response == "ERROR:NO_VALIDATOR":
                Log("Response", f"{Red('Validator Not Online')} — Start Validator_Node.py First", "red")
            elif Response == "ERROR:AUTH_REJECTED":
                Log("Response", f"{Red('Auth Rejected')} — Wrong Password Sent", "red")
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
    Val_IP = sys.argv[1] if len(sys.argv) > 1 else VALIDATOR_IP
    Run_User_Node(Val_IP)
