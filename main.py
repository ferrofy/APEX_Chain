import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel   import Panel
from rich.text    import Text
from rich.align   import Align
from rich.rule    import Rule

Console_Out = Console()

def Show_Splash():
    Console_Out.clear()
    Console_Out.print()

    Title = Text()
    Title.append("APEX ⛓  ", style="bold yellow")
    Title.append("  Blockchain Node System  ", style="bold cyan")
    Title.append("⛓  ", style="bold yellow")

    Subtitle = Text(
        "Decentralized  ·  Peer-To-Peer  ·  SHA-256 Verified",
        style="dim white",
        justify="center",
    )

    Console_Out.print(Panel(
        Align.center(Title),
        border_style="cyan",
        padding=(0, 4),
    ))
    Console_Out.print(Align.center(Subtitle))
    Console_Out.print()
    Console_Out.print(Rule(style="dim cyan"))
    Console_Out.print()

    Console_Out.print(Panel(
        "\n"
        "  [bold cyan]\\[1][/bold cyan]  [white]TX Node[/white]  "
        "[dim]—  Transmitter  ·  Mine & Send Blocks[/dim]\n\n"
        "  [bold magenta]\\[2][/bold magenta]  [white]RX Node[/white]  "
        "[dim]—  Receiver    ·  Listen & Validate Blocks[/dim]\n\n"
        "  [bold red]\\[Q][/bold red]  [white]Quit[/white]\n",
        title="[bold white]Select Node Type[/bold white]",
        border_style="bright_blue",
        padding=(0, 2),
    ))
    Console_Out.print()

def Main():
    while True:
        Show_Splash()
        Choice = Console_Out.input("  [bold yellow]>[/bold yellow] ").strip().lower()

        if Choice == "1":
            Console_Out.print()
            Console_Out.print(Panel(
                "  [cyan]Starting TX Node...[/cyan]",
                border_style="cyan",
                padding=(0, 2),
            ))
            Console_Out.print()
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Files", "Python"))
            from Files.Python import TX
            TX.Start_TX()
            break

        elif Choice == "2":
            Console_Out.print()
            Console_Out.print(Panel(
                "  [magenta]Starting RX Node...[/magenta]",
                border_style="magenta",
                padding=(0, 2),
            ))
            Console_Out.print()
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "Files", "Python"))
            from Files.Python import RX
            RX.Start_RX()
            break

        elif Choice in ("q", "quit", "exit"):
            Console_Out.print("\n  [bold red]Goodbye.[/bold red]\n")
            break

        else:
            Console_Out.print("  [red]Invalid Choice. Please Enter 1, 2, Or Q.[/red]\n")
            Console_Out.input("  [dim]Press Enter To Continue...[/dim]")

Main()
