import socket
import os
import sys
import time
import json
import hashlib
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console   import Console
from rich.panel     import Panel
from rich.table     import Table
from rich.layout    import Layout
from rich.live      import Live
from rich.text      import Text
from rich.rule      import Rule
from rich.prompt    import Prompt
from rich.align     import Align

Port      = 5000
Folder    = "Blocks"
BANNER_W  = 60
MAX_LOGS  = 18

Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"

Chain       = []
RX_Sock     = None
RX_IP       = None
Node_IP_G   = None

Log_Lines   = []
Log_Lock    = threading.Lock()
Chain_Lock  = threading.Lock()

Console_Out = Console()

def Add_Log(Msg, Style="white"):
    Ts = time.strftime("%H:%M:%S")
    with Log_Lock:
        Log_Lines.append(f"[dim]{Ts}[/dim]  [{Style}]{Msg}[/{Style}]")
        if len(Log_Lines) > MAX_LOGS:
            Log_Lines.pop(0)

def Get_Local_IP():
    S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        S.connect(("8.8.8.8", 80))
        IP = S.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        S.close()
    return IP

def SHA256(Text_In):
    return hashlib.sha256(Text_In.encode("utf-8")).hexdigest()

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256(Raw)

def Init_Folder():
    os.makedirs(Folder, exist_ok=True)

def Load_Chain():
    Chain_Data = []
    if not os.path.exists(Folder):
        return Chain_Data
    Files = [F for F in os.listdir(Folder) if F.endswith(".json")]
    for File in Files:
        try:
            with open(os.path.join(Folder, File), "r") as F:
                Block = json.load(F)
                Chain_Data.append(Block)
        except Exception:
            pass
    Chain_Data.sort(key=lambda B: B["Block"])
    return Chain_Data

def Get_Last_Block(Chain_Data):
    if not Chain_Data:
        return None
    return Chain_Data[-1]

def Build_Genesis_Block(Node_IP):
    Index       = 0
    Timestamp   = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Data        = {"Message": "Genesis Block", "Node": Node_IP}
    Prev_Hash   = "0" * 64
    Hash        = Compute_Block_Hash(Index, Timestamp, Data, Prev_Hash)
    return {
        "Block":     Index,
        "Timestamp": Timestamp,
        "Data":      Data,
        "Prev_Hash": Prev_Hash,
        "Hash":      Hash
    }

def Build_Next_Block(Previous_Block, Message, Node_IP):
    Index     = Previous_Block["Block"] + 1
    Timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Data      = {
        "Message":    Message,
        "Node":       Node_IP,
        "Block_Time": Timestamp
    }
    Prev_Hash = Previous_Block["Hash"]
    Hash      = Compute_Block_Hash(Index, Timestamp, Data, Prev_Hash)
    return {
        "Block":     Index,
        "Timestamp": Timestamp,
        "Data":      Data,
        "Prev_Hash": Prev_Hash,
        "Hash":      Hash
    }

def Save_Block(Block):
    File_Name = f"block_{Block['Block']}.json"
    Path      = os.path.join(Folder, File_Name)
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return File_Name

def Send_Length_Prefixed(Sock, Payload_Bytes):
    Length = len(Payload_Bytes)
    Header = Length.to_bytes(4, byteorder="big")
    Sock.sendall(Header + Payload_Bytes)

def Send_Block(Sock, Block):
    Payload = json.dumps(Block).encode("utf-8")
    Send_Length_Prefixed(Sock, Payload)

def Make_Header_Panel():
    Status_Color = "green" if RX_IP else "red"
    Status_Text  = f"[{Status_Color}]Connected → {RX_IP}[/{Status_Color}]" if RX_IP else "[red]Not Connected[/red]"
    Content = (
        f"  [bold cyan]Node IP[/bold cyan]  :  [white]{Node_IP_G}[/white]   "
        f"[bold cyan]Port[/bold cyan]  :  [white]{Port}[/white]   "
        f"[bold cyan]Blocks[/bold cyan]  :  [white]{Folder}/[/white]   "
        f"[bold cyan]RX[/bold cyan]  :  {Status_Text}"
    )
    return Panel(Content, title="[bold yellow]⛓  FerroFy TX — Transmitter Node[/bold yellow]", border_style="cyan", padding=(0, 1))

def Make_Chain_Table():
    Table_Out = Table(
        title="[bold white]Blockchain[/bold white]",
        border_style="bright_blue",
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    Table_Out.add_column("#",          style="bold yellow", width=4,  justify="right")
    Table_Out.add_column("Timestamp",  style="dim white",   width=22, no_wrap=True)
    Table_Out.add_column("Message",    style="white",       ratio=2)
    Table_Out.add_column("Hash",       style="green",       width=20, no_wrap=True)
    Table_Out.add_column("Prev Hash",  style="dim green",   width=20, no_wrap=True)

    with Chain_Lock:
        Visible = Chain[-12:] if len(Chain) > 12 else Chain[:]

    for B in Visible:
        Msg = B["Data"].get("Message", "—")
        Table_Out.add_row(
            str(B["Block"]),
            B["Timestamp"],
            Msg,
            B["Hash"][:18] + "…",
            B["Prev_Hash"][:18] + "…",
        )
    return Table_Out

def Make_Log_Panel():
    with Log_Lock:
        Lines = list(Log_Lines)
    Body = "\n".join(Lines) if Lines else "[dim]No Events Yet...[/dim]"
    return Panel(Body, title="[bold white]Event Log[/bold white]", border_style="bright_blue", padding=(0, 1))

def Connect_To_RX(Target_IP):
    global RX_Sock, RX_IP
    Console_Out.print(f"\n  [cyan]Connecting To {Target_IP}:{Port}...[/cyan]")
    try:
        S = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        S.settimeout(5.0)
        S.connect((Target_IP, Port))

        Greeting = S.recv(1024).decode()
        if Greeting != Handshake_A:
            Console_Out.print(f"  [red]Auth Failed — Unexpected Handshake: '{Greeting}'[/red]")
            S.close()
            return False

        S.send(Handshake_B.encode())
        S.settimeout(None)

        RX_Sock = S
        RX_IP   = Target_IP
        Console_Out.print(f"  [bold green]✓ Connected To {Target_IP}[/bold green]")
        return True

    except Exception as E:
        Console_Out.print(f"  [red]Failed — {E}[/red]")
        return False

def Start_TX():
    global Chain, RX_Sock, RX_IP, Node_IP_G

    Init_Folder()
    Node_IP_G = Get_Local_IP()

    Console_Out.clear()
    Console_Out.print(Panel(
        f"\n  [bold cyan]TX Node[/bold cyan]  |  IP: [white]{Node_IP_G}[/white]  |  Port: [white]{Port}[/white]\n",
        title="[bold yellow]⛓  FerroFy Transmitter[/bold yellow]",
        border_style="cyan",
        padding=(0, 2),
    ))
    Console_Out.print()

    while True:
        Target = Prompt.ask("  [bold yellow]RX Node IP[/bold yellow]").strip()
        if not Target:
            Console_Out.print("  [red]IP Cannot Be Empty.[/red]")
            continue
        if Connect_To_RX(Target):
            Add_Log(f"Connected To RX @ {Target}", "green")
            break
        Retry = Prompt.ask("  [bold]Retry? (y/n)[/bold]").strip().lower()
        if Retry != "y":
            Console_Out.print("  [red]Exiting — No Connection Established.[/red]")
            return

    Chain = Load_Chain()

    if not Chain:
        Genesis   = Build_Genesis_Block(Node_IP_G)
        with Chain_Lock:
            Chain.append(Genesis)
        File_Name = Save_Block(Genesis)
        Add_Log(f"Genesis Block Created → {File_Name}", "yellow")
        try:
            Send_Block(RX_Sock, Genesis)
            Add_Log(f"Genesis Sent → {RX_IP}", "green")
        except Exception as E:
            Add_Log(f"Genesis Send Failed | {E}", "red")
    else:
        Add_Log(f"Loaded {len(Chain)} Existing Block(s)", "cyan")
        with Chain_Lock:
            Last = Get_Last_Block(Chain)
        Add_Log(f"Tip: Block {Last['Block']} | Hash: {Last['Hash'][:16]}…", "dim")
        Add_Log(f"Syncing {len(Chain)} Block(s) To {RX_IP}…", "cyan")
        with Chain_Lock:
            Blocks_To_Send = list(Chain)
        for Block in Blocks_To_Send:
            try:
                Send_Block(RX_Sock, Block)
                Add_Log(f"Sent Block {Block['Block']} → {RX_IP}", "green")
                time.sleep(0.05)
            except Exception as E:
                Add_Log(f"Block {Block['Block']} Send Failed | {E}", "red")
                break

    Add_Log("Ready — Type A Message Below To Mine A Block", "bold white")

    with Live(
        console=Console_Out,
        refresh_per_second=4,
        screen=False,
        vertical_overflow="visible",
    ) as Live_Display:
        while True:
            Layout_Root = Layout()
            Layout_Root.split_column(
                Layout(Make_Header_Panel(),  name="Header",  size=3),
                Layout(Make_Chain_Table(),   name="Chain"),
                Layout(Make_Log_Panel(),     name="Log",     size=MAX_LOGS + 2),
            )
            Live_Display.update(Layout_Root)

            try:
                Live_Display.stop()
                Message = Console_Out.input("\n  [bold yellow]📝 Message[/bold yellow] [dim]>[/dim] ").strip()
                Live_Display.start()
            except KeyboardInterrupt:
                Add_Log("TX Node Shutting Down…", "red")
                Live_Display.update(Layout_Root)
                if RX_Sock:
                    RX_Sock.close()
                break

            if not Message:
                Add_Log("Empty Message Skipped.", "dim")
                continue

            with Chain_Lock:
                Last_Block = Get_Last_Block(Chain)
                New_Block  = Build_Next_Block(Last_Block, Message, Node_IP_G)
                Chain.append(New_Block)

            File_Name = Save_Block(New_Block)
            Add_Log(f"⛏  Mined Block {New_Block['Block']} → {File_Name}", "yellow")

            if RX_Sock:
                try:
                    Send_Block(RX_Sock, New_Block)
                    Add_Log(f"✓ Sent Block {New_Block['Block']} → {RX_IP}", "green")
                except Exception as E:
                    Add_Log(f"Send Failed | {E}", "red")
                    RX_Sock = None
            else:
                Add_Log("Not Connected To RX — Block Saved Locally.", "dim")