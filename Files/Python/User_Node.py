import datetime as _datetime
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from Gui_Theme import (
    BlockchainHeader,
    COLORS,
    append_log,
    install_dark_theme,
    make_panel,
    make_scrolled_text,
    status_color,
    style_text_widget,
)
from Protocol import DOC_NODE_PORT, get_local_ip, now_utc, parse_fixed_endpoint, request

DEFAULT_DOC_PORT = DOC_NODE_PORT
RETRY_SECONDS = 3

FIELDS = [
    ("name", "Name", "entry"),
    ("problem", "Problem", "text"),
    ("symptoms", "Symptoms", "text"),
    ("disease", "Disease", "entry"),
    ("date", "Date", "entry"),
    ("solution", "Solution", "text"),
    ("extra_notes", "Extra Notes", "text_long"),
]


def send_user_data(doc_host, doc_port, form_data, timeout=600.0):
    local_ip = get_local_ip()
    packet = {
        "type": "USER_DATA",
        "from": f"user:{local_ip}",
        "host": local_ip,
        "payload": {
            "user_node": f"user:{local_ip}",
            "sent_at": now_utc(),
            **form_data,
        },
    }
    return request(doc_host, doc_port, packet, timeout=timeout, connect_timeout=4.0)


class UserNodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FerroFy User Node")
        self.root.geometry("980x780")
        self.root.minsize(860, 700)
        install_dark_theme(root)

        self.stop_event = threading.Event()
        self.worker = None
        self.inputs = {}

        self._build()

    def _build(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = BlockchainHeader(
            self.root,
            "FERROFY USER NODE",
            f"LOCAL IP {get_local_ip()}  /  DOC PORT {DEFAULT_DOC_PORT}  /  SIGNED JSON REQUEST",
        )
        header.grid(row=0, column=0, sticky="ew")

        shell = ttk.Frame(self.root, padding=18, style="TFrame")
        shell.grid(row=1, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=2)
        shell.rowconfigure(0, weight=1)

        left = make_panel(shell, padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="DOC NODE TARGET", style="PanelAccent.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(left).grid(row=1, column=0, sticky="ew", pady=(10, 14))

        ttk.Label(left, text="Doc Node IP / Host", style="Panel.TLabel").grid(row=2, column=0, sticky="w")
        self.doc_ip = ttk.Entry(left)
        self.doc_ip.insert(0, "127.0.0.1")
        self.doc_ip.grid(row=3, column=0, sticky="ew", pady=(5, 12))

        ttk.Label(
            left,
            text=f"User -> Doc uses fixed port {DEFAULT_DOC_PORT}",
            style="PanelMuted.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(0, 16))

        self.status_bar = tk.Frame(left, bg=COLORS["panel_2"], highlightthickness=1, highlightbackground=COLORS["line"])
        self.status_bar.grid(row=5, column=0, sticky="ew", pady=(4, 16))
        self.status_dot = tk.Canvas(self.status_bar, width=18, height=18, highlightthickness=0, bg=COLORS["panel_2"])
        self.status_dot.pack(side="left", padx=(12, 7), pady=12)
        self.status_text = tk.Label(
            self.status_bar,
            text="READY",
            bg=COLORS["panel_2"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.status_text.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._draw_status_dot("info")

        self.send_button = ttk.Button(left, text="SEND TO DOC NODE", style="Accent.TButton", command=self.start_send)
        self.send_button.grid(row=6, column=0, sticky="ew", pady=(0, 10))

        self.stop_button = ttk.Button(left, text="STOP RETRY", command=self.stop_retry, state="disabled")
        self.stop_button.grid(row=7, column=0, sticky="ew")

        ttk.Label(left, text="TRANSMISSION LOG", style="PanelAccent.TLabel").grid(row=8, column=0, sticky="w", pady=(22, 8))
        log_container, self.log_box = make_scrolled_text(left, height=13, readonly=True, font=("Consolas", 9))
        log_container.grid(row=9, column=0, sticky="nsew")
        left.rowconfigure(9, weight=1)

        form = make_panel(shell, padding=18, style="Panel2.TFrame")
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(2, weight=1)
        form.rowconfigure(3, weight=1)
        form.rowconfigure(5, weight=1)
        form.rowconfigure(6, weight=1)

        ttk.Label(form, text="PATIENT / CASE DATA", style="PanelAccent.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Separator(form).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 12))

        row = 2
        for key, label, kind in FIELDS:
            ttk.Label(form, text=label, style="Panel2.TLabel").grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=6)
            if kind == "entry":
                widget = ttk.Entry(form)
                widget.grid(row=row, column=1, sticky="ew", pady=6)
            else:
                h = 5 if kind == "text_long" else 3
                container, widget = make_scrolled_text(form, height=h)
                container.grid(row=row, column=1, sticky="nsew", pady=6)
            self.inputs[key] = widget
            row += 1

        self.inputs["date"].insert(0, _datetime.date.today().isoformat())
        self.set_status("Ready. Fill required fields and send.", "info")
        append_log(self.log_box, "User Node initialized.")

    def read_form(self):
        data = {}
        for key, _label, _kind in FIELDS:
            widget = self.inputs[key]
            if isinstance(widget, tk.Text):
                value = widget.get("1.0", "end").strip()
            else:
                value = widget.get().strip()
            data[key] = value
        return data

    def start_send(self):
        if self.worker and self.worker.is_alive():
            return

        form_data = self.read_form()
        if not form_data["name"] or not form_data["problem"]:
            messagebox.showwarning("Missing Data", "Name and Problem are required.")
            return

        try:
            doc_host, doc_port = parse_fixed_endpoint(self.doc_ip.get().strip(), DEFAULT_DOC_PORT, "Doc Node")
        except Exception as exc:
            messagebox.showerror("Invalid Doc Node", str(exc))
            return

        self.stop_event.clear()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.set_status("Connecting to Doc Node.", "warn")
        self.log(f"Queueing request for {doc_host}:{doc_port}")

        self.worker = threading.Thread(
            target=self._send_loop,
            args=(doc_host, doc_port, form_data),
            daemon=True,
        )
        self.worker.start()

    def stop_retry(self):
        self.stop_event.set()
        self.set_status("Stopping retry loop.", "warn")

    def _send_loop(self, doc_host, doc_port, form_data):
        attempt = 1
        while not self.stop_event.is_set():
            self.set_status(f"Attempt {attempt}: waiting for Doc Node.", "warn")
            self.log(f"Attempt {attempt} -> {doc_host}:{doc_port}")
            try:
                response = send_user_data(doc_host, doc_port, form_data)
                if response and response.get("ok"):
                    self.set_status(
                        f"Approved. Doc {response.get('doc_id')} / Block {response.get('block_index')}",
                        "ok",
                    )
                    self.log(f"Approved by Doc Node. Block hash {str(response.get('block_hash'))[:32]}...")
                else:
                    error = response.get("error", "request rejected") if response else "no response"
                    self.set_status(f"Rejected: {error}", "error")
                    self.log(f"Rejected by Doc Node: {error}")
                break
            except Exception as exc:
                self.set_status(f"No connection. Retrying in {RETRY_SECONDS}s.", "warn")
                self.log(f"Connection failed: {exc}")
                for _ in range(RETRY_SECONDS * 10):
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)
                attempt += 1

        self.root.after(0, self._reset_buttons)

    def set_status(self, message, kind="info"):
        def update():
            self.status_text.configure(text=message.upper(), fg=status_color(kind))
            self._draw_status_dot(kind)

        self.root.after(0, update)

    def _draw_status_dot(self, kind):
        self.status_dot.delete("all")
        color = status_color(kind)
        self.status_dot.create_oval(3, 3, 15, 15, fill=color, outline=color)

    def log(self, message):
        self.root.after(0, lambda: append_log(self.log_box, f"[{time.strftime('%H:%M:%S')}] {message}"))

    def _reset_buttons(self):
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")


def Start_User():
    root = tk.Tk()
    UserNodeApp(root)
    root.mainloop()


if __name__ == "__main__":
    Start_User()
