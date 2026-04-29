import tkinter as tk
from tkinter import ttk


COLORS = {
    "bg": "#070B14",
    "panel": "#0D1424",
    "panel_2": "#111B2E",
    "panel_3": "#17243A",
    "line": "#263A5E",
    "line_soft": "#1B2B46",
    "text": "#E7EEFB",
    "muted": "#8EA2C3",
    "dim": "#607493",
    "accent": "#00E5FF",
    "accent_2": "#56F0B6",
    "warning": "#FFCC66",
    "danger": "#FF5E7A",
    "input": "#0A1020",
    "input_border": "#2D456E",
}

FONTS = {
    "title": ("Segoe UI", 21, "bold"),
    "subtitle": ("Segoe UI", 10),
    "body": ("Segoe UI", 10),
    "label": ("Segoe UI", 10, "bold"),
    "small": ("Segoe UI", 9),
    "mono": ("Consolas", 10),
    "mono_small": ("Consolas", 9),
}


def install_dark_theme(root):
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=FONTS["body"], background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Panel.TFrame", background=COLORS["panel"], relief="flat")
    style.configure("Panel2.TFrame", background=COLORS["panel_2"], relief="flat")
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("Panel2.TLabel", background=COLORS["panel_2"], foreground=COLORS["text"])
    style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=FONTS["title"])
    style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=FONTS["small"])
    style.configure("PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=FONTS["small"])
    style.configure("Accent.TLabel", background=COLORS["bg"], foreground=COLORS["accent"], font=FONTS["label"])
    style.configure("PanelAccent.TLabel", background=COLORS["panel"], foreground=COLORS["accent"], font=FONTS["label"])

    style.configure(
        "TEntry",
        fieldbackground=COLORS["input"],
        background=COLORS["input"],
        foreground=COLORS["text"],
        bordercolor=COLORS["input_border"],
        insertcolor=COLORS["accent"],
        relief="flat",
        padding=8,
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", COLORS["panel_3"]), ("readonly", COLORS["input"])],
        foreground=[("disabled", COLORS["dim"])],
        bordercolor=[("focus", COLORS["accent"])],
    )

    style.configure(
        "TButton",
        background=COLORS["panel_3"],
        foreground=COLORS["text"],
        bordercolor=COLORS["line"],
        focusthickness=0,
        padding=(14, 9),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", COLORS["line"]), ("pressed", COLORS["input"])],
        foreground=[("disabled", COLORS["dim"]), ("active", COLORS["text"])],
    )
    style.configure("Accent.TButton", background=COLORS["accent"], foreground="#031018", bordercolor=COLORS["accent"])
    style.map("Accent.TButton", background=[("active", "#4EF4FF"), ("pressed", "#00BFD4")])
    style.configure("Success.TButton", background=COLORS["accent_2"], foreground="#03140F", bordercolor=COLORS["accent_2"])
    style.map("Success.TButton", background=[("active", "#78FFD0"), ("pressed", "#2CCF96")])
    style.configure("Danger.TButton", background=COLORS["danger"], foreground="#18030A", bordercolor=COLORS["danger"])
    style.map("Danger.TButton", background=[("active", "#FF7D94"), ("pressed", "#D94560")])

    style.configure("Horizontal.TSeparator", background=COLORS["line"])
    return style


class BlockchainHeader(tk.Canvas):
    def __init__(self, master, title, subtitle, height=116):
        super().__init__(
            master,
            height=height,
            highlightthickness=0,
            bg=COLORS["bg"],
            bd=0,
        )
        self.title = title
        self.subtitle = subtitle
        self.bind("<Configure>", self._draw)

    def _draw(self, _event=None):
        self.delete("all")
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)

        for x in range(0, width, 42):
            self.create_line(x, 0, x - 64, height, fill=COLORS["line_soft"])
        for y in range(12, height, 28):
            self.create_line(0, y, width, y, fill="#0B1324")

        nodes = [
            (width - 260, 30),
            (width - 178, 66),
            (width - 94, 34),
            (width - 48, 82),
        ]
        for index, (x, y) in enumerate(nodes):
            if index:
                px, py = nodes[index - 1]
                self.create_line(px, py, x, y, fill=COLORS["accent"], width=2)
            self.create_rectangle(x - 17, y - 17, x + 17, y + 17, outline=COLORS["accent"], width=2)
            self.create_text(x, y, text=str(index), fill=COLORS["accent_2"], font=FONTS["mono_small"])

        self.create_text(28, 34, text=self.title, anchor="w", fill=COLORS["text"], font=FONTS["title"])
        self.create_text(30, 72, text=self.subtitle, anchor="w", fill=COLORS["muted"], font=FONTS["subtitle"])
        self.create_line(28, height - 15, min(320, width - 28), height - 15, fill=COLORS["accent"], width=3)


def make_panel(master, padding=16, style="Panel.TFrame"):
    frame = ttk.Frame(master, padding=padding, style=style)
    return frame


def style_text_widget(widget, readonly=False, height=None):
    widget.configure(
        bg=COLORS["input"],
        fg=COLORS["text"],
        insertbackground=COLORS["accent"],
        selectbackground=COLORS["line"],
        selectforeground=COLORS["text"],
        relief="flat",
        bd=1,
        highlightthickness=1,
        highlightbackground=COLORS["input_border"],
        highlightcolor=COLORS["accent"],
        font=FONTS["body"],
        padx=10,
        pady=8,
    )
    if height is not None:
        widget.configure(height=height)
    if readonly:
        widget.configure(state="disabled")


def set_text_value(widget, value, readonly=True):
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    if readonly:
        widget.configure(state="disabled")


def append_log(widget, line):
    widget.configure(state="normal")
    widget.insert("end", line + "\n")
    widget.see("end")
    widget.configure(state="disabled")


def status_color(kind):
    return {
        "ok": COLORS["accent_2"],
        "warn": COLORS["warning"],
        "error": COLORS["danger"],
        "info": COLORS["accent"],
    }.get(kind, COLORS["muted"])
