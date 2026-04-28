import sys
import os
import socket
import json
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NODE_TYPE      = "USER_NODE"
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

def Check_Validator_Online():
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(2)
        S.connect((VALIDATOR_IP, VALIDATOR_PORT))
        S.close()
        return True
    except Exception:
        return False

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
    Packet = json.dumps({"Wallet": Wallet, "Data": Data}).encode("utf-8")

    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(30)
        S.connect((VALIDATOR_IP, VALIDATOR_PORT))
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

def Run_User_Node():
    os.system("")
    Print_Logo()

    Section("Checking Validator Node Connection")
    Retries = 0
    while True:
        if Check_Validator_Online():
            Log("Validator", f"{Green('Online')}  ✓  Connected To {VALIDATOR_IP}:{VALIDATOR_PORT}", "green")
            break
        Retries += 1
        Log("Validator", f"{Red('Offline')} — Retry {Retries}... (Start Validator_Node.py First)", "red")
        time.sleep(3)

    Section("User Node — Wallet Setup")
    Wallet = Get_Wallet()
    Info("Wallet Address", Cyan(Wallet[:16] + "...."))

    while True:
        Data = Get_Request_Data()

        if not Data:
            Log("Warning", "No Data Fields Entered.  Request Cancelled.", "yellow")
        else:
            Section("Sending Request To Validator")
            Info("Validator IP",   Cyan(VALIDATOR_IP))
            Info("Validator Port", str(VALIDATOR_PORT))
            Info("Wallet",         Cyan(Wallet[:16] + "...."))
            Info("Fields",         str(len(Data)))
            for K, V in Data.items():
                Info(f"  {K}", Dim(V))

            print()
            Log("Sending", f"Connecting To Validator At {VALIDATOR_IP}:{VALIDATOR_PORT}...", "cyan")
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
    Run_User_Node()
