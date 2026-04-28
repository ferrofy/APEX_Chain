import socket
import os
import sys
import threading
import time
import json
import hashlib

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel   import Panel
from rich.table   import Table
from rich.layout  import Layout
from rich.live    import Live

Host     = "0.0.0.0"
Port     = 5000
Folder   = "Blocks"
MAX_LOGS = 18

Handshake_A = "Mine_RX"
Handshake_B = "Mine_TX"

Chain        = []
Chain_Lock   = threading.Lock()
Peers        = []
Peers_Lock   = threading.Lock()
Log_Lines    = []
Log_Lock     = threading.Lock()

Console_Out  = Console()
Live_Display = None

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


def Calculate_Hash(Block):
    Raw = f"{Block['Block']}{Block['Timestamp']}{json.dumps(Block['Data'], sort_keys=True)}{Block['Prev_Hash']}"
    return SHA256(Raw)

def Save_Block(Block):
    os.makedirs(Folder, exist_ok=True)
    Path = os.path.join(Folder, f"block_{Block['Block']}.json")
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return Path

def Recv_Length_Prefixed(Sock):
    Header = b""
    while len(Header) < 4:
        Chunk = Sock.recv(4 - len(Header))
        if not Chunk:
            return None
        Header += Chunk
    Length = int.from_bytes(Header, "big")
    Buf    = b""
    while len(Buf) < Length:
        Chunk = Sock.recv(min(65536, Length - len(Buf)))
        if not Chunk:
            return None
        Buf += Chunk
    return Buf

def Validate_Genesis(Block):
    if Block.get("Block") != 0:
        return False, "Genesis Index Must Be 0"
    if Block.get("Prev_Hash") not in ("", "0" * 64):
        return False, "Genesis Prev_Hash Must Be Empty Or 64 Zeros"
    return True, "Valid"

def Validate_Block(Block, Prev_Block):
    if Block["Block"] != Prev_Block["Block"] + 1:
        return False, f"Index Mismatch (Expected {Prev_Block['Block'] + 1}, Got {Block['Block']})"
    if Block["Prev_Hash"] != Prev_Block["Hash"]:
        return False, "Prev_Hash Mismatch"
    Recomputed = Calculate_Hash(Block)
    if Recomputed != Block["Hash"]:
        return False, "Hash Recompute Failed"
    return True, "Valid"

def Make_Header_Panel(Node_IP):
    with Peers_Lock:
        Peer_Count = len(Peers)
    with Chain_Lock:
        Block_Count = len(Chain)
    Content = (
        f"  [bold cyan]Node IP[/bold cyan]  :  [white]{Node_IP}[/white]   "
        f"[bold cyan]Port[/bold cyan]  :  [white]{Port}[/white]   "
        f"[bold cyan]Blocks[/bold cyan]  :  [white]{Folder}/[/white]   "
        f"[bold cyan]TX Peers[/bold cyan]  :  [green]{Peer_Count}[/green]   "
        f"[bold cyan]Chain Length[/bold cyan]  :  [yellow]{Block_Count}[/yellow]"
    )
    return Panel(Content, title="[bold magenta]⛓  FerroFy RX — Receiver Node[/bold magenta]", border_style="magenta", padding=(0, 1))

def Make_Peers_Table():
    Table_Out = Table(
        title="[bold white]Connected TX Peers[/bold white]",
        border_style="bright_magenta",
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )
    Table_Out.add_column("TX IP",       style="cyan",      width=20)
    Table_Out.add_column("Connected At", style="dim white", width=22)
    Table_Out.add_column("Status",       style="green",     width=12)

    with Peers_Lock:
        Visible = list(Peers)

    for P in Visible:
        Table_Out.add_row(P["IP"], P["Since"], "[green]● Active[/green]")

    if not Visible:
        Table_Out.add_row("[dim]—[/dim]", "[dim]—[/dim]", "[dim]Waiting…[/dim]")

    return Table_Out

def Make_Chain_Table():
    Table_Out = Table(
        title="[bold white]Received Blockchain[/bold white]",
        border_style="bright_blue",
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    Table_Out.add_column("#",           style="bold yellow", width=4,  justify="right")
    Table_Out.add_column("Timestamp",   style="dim white",   width=22, no_wrap=True)
    Table_Out.add_column("Message",     style="white",       ratio=2)
    Table_Out.add_column("Hash",        style="green",       width=20, no_wrap=True)
    Table_Out.add_column("Status",      style="bold",        width=14, no_wrap=True)

    with Chain_Lock:
        Visible = Chain[-10:] if len(Chain) > 10 else Chain[:]

    for B in Visible:
        Msg    = B["Data"].get("Message", "—")
        Status = "[yellow]⛏ Genesis[/yellow]" if B["Block"] == 0 else "[green]✓ Valid[/green]"
        Table_Out.add_row(
            str(B["Block"]),
            B["Timestamp"],
            Msg,
            B["Hash"][:18] + "…",
            Status,
        )

    if not Visible:
        Table_Out.add_row("[dim]—[/dim]", "[dim]—[/dim]", "[dim]Waiting For Blocks…[/dim]", "[dim]—[/dim]", "[dim]—[/dim]")

    return Table_Out

def Make_Log_Panel():
    with Log_Lock:
        Lines = list(Log_Lines)
    Body = "\n".join(Lines) if Lines else "[dim]No Events Yet...[/dim]"
    return Panel(Body, title="[bold white]Event Log[/bold white]", border_style="bright_blue", padding=(0, 1))

def Build_Layout(Node_IP):
    Root = Layout()
    Root.split_column(
        Layout(Make_Header_Panel(Node_IP), name="Header", size=3),
        Layout(name="Middle",              ratio=1),
        Layout(Make_Log_Panel(),           name="Log",    size=MAX_LOGS + 2),
    )
    Root["Middle"].split_row(
        Layout(Make_Peers_Table(), name="Peers", ratio=1),
        Layout(Make_Chain_Table(), name="Chain", ratio=3),
    )
    return Root

def Handle_TX(Client_Socket, Addr, Node_IP):
    global Chain

    Add_Log(f"TX Node Connecting From {Addr[0]}…", "cyan")

    try:
        Client_Socket.settimeout(5.0)
        Client_Socket.send(Handshake_A.encode())
        Response = Client_Socket.recv(1024).decode()
        if Response != Handshake_B:
            Add_Log(f"Auth Failed — Wrong Response From {Addr[0]}: '{Response}'", "red")
            Client_Socket.close()
            return
        Client_Socket.settimeout(None)
        Add_Log(f"✓ {Addr[0]} Verified As TX Node", "green")
    except Exception as E:
        Add_Log(f"Handshake Failed With {Addr[0]} | {E}", "red")
        Client_Socket.close()
        return

    with Peers_Lock:
        Peers.append({"IP": Addr[0], "Since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

    Add_Log(f"Listening For Blocks From {Addr[0]}…", "white")

    while True:
        try:
            Raw = Recv_Length_Prefixed(Client_Socket)
            if Raw is None:
                Add_Log(f"TX Node {Addr[0]} Disconnected.", "dim")
                break

            Block = json.loads(Raw.decode("utf-8"))

            if not isinstance(Block, dict) or "Block" not in Block:
                Add_Log(f"Invalid Packet From {Addr[0]}", "red")
                continue

            with Chain_Lock:
                Local_Chain = list(Chain)

            if not Local_Chain:
                G_Ok, G_Reason = Validate_Genesis(Block)
                if G_Ok:
                    Save_Block(Block)
                    Add_Log(f"⛏  Genesis Block Received From {Addr[0]}", "yellow")
                    Add_Log(f"   Hash: {Block['Hash'][:32]}…", "dim")
                    with Chain_Lock:
                        Chain.append(Block)
                else:
                    Add_Log(f"Genesis Rejected | {G_Reason}", "red")
            else:
                with Chain_Lock:
                    Prev = Chain[-1]
                V_Ok, V_Reason = Validate_Block(Block, Prev)
                if V_Ok:
                    Save_Block(Block)
                    Add_Log(f"✓ Block {Block['Block']} Received From {Addr[0]}", "green")
                    Add_Log(f"   Hash: {Block['Hash'][:32]}…", "dim")
                    with Chain_Lock:
                        Chain.append(Block)
                else:
                    Add_Log(f"✗ Block {Block['Block']} Rejected | {V_Reason}", "red")

        except Exception as E:
            Add_Log(f"Lost Connection To {Addr[0]} | {E}", "red")
            break

    with Peers_Lock:
        Peers[:] = [P for P in Peers if P["IP"] != Addr[0]]

    Client_Socket.close()

def Accept_Loop(Server_Socket, Node_IP):
    while True:
        try:
            Client_Socket, Addr = Server_Socket.accept()
            Client_Socket.settimeout(None)
            Thread = threading.Thread(
                target=Handle_TX,
                args=(Client_Socket, Addr, Node_IP),
                daemon=True,
            )
            Thread.start()
        except Exception as E:
            Add_Log(f"Accept Error | {E}", "red")

def Start_RX():
    Node_IP = Get_Local_IP()

    Add_Log(f"RX Node Started At {Node_IP}:{Port}", "bold magenta")
    Add_Log(f"Share IP [bold white]{Node_IP}[/bold white] With TX Node To Connect", "cyan")

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(10)

    Add_Log(f"Listening On {Host}:{Port}…", "green")

    Accept_Thread = threading.Thread(
        target=Accept_Loop,
        args=(Server_Socket, Node_IP),
        daemon=True,
    )
    Accept_Thread.start()

    try:
        with Live(
            console=Console_Out,
            refresh_per_second=4,
            screen=False,
            vertical_overflow="visible",
        ) as Live_Ctx:
            while True:
                Live_Ctx.update(Build_Layout(Node_IP))
                time.sleep(0.25)
    except KeyboardInterrupt:
        Add_Log("RX Node Shutting Down…", "red")
        Server_Socket.close()
        Console_Out.print("\n  [bold red]RX Node Stopped.[/bold red]\n")


if __name__ == "__main__":
    Start_RX()