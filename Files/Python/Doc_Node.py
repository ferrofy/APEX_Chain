import json
import os
import random
import socket
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from Blockchain import canonical_json, sha256_text, sha512_text, token_cost_for_fields
from Gui_Theme import (
    BlockchainHeader,
    COLORS,
    append_log,
    install_dark_theme,
    make_panel,
    make_scrolled_frame,
    make_scrolled_text,
    set_text_value,
    status_color,
    style_text_widget,
)
from Protocol import (
    DATA_NODE_PORT,
    DEFAULT_LISTEN_HOST,
    DOC_NODE_PORT,
    get_local_ip,
    now_utc,
    parse_fixed_endpoint,
    recv_packet,
    request,
    send_packet,
)

PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(PYTHON_DIR, "..", ".."))

DEFAULT_DOC_PORT = DOC_NODE_PORT
DEFAULT_DATA_PORT = DATA_NODE_PORT
DEFAULT_DOC_FOLDER = os.path.join(PROJECT_ROOT, "Files", "Documents")
PENDING_TIMEOUT_SECONDS = 900

FORM_KEYS = [
    ("name", "Name"),
    ("problem", "Problem"),
    ("symptoms", "Symptoms"),
    ("disease", "Disease"),
    ("date", "Date"),
    ("solution", "Solution"),
    ("extra_notes", "Extra Notes"),
]


class PendingRequest:
    def __init__(self, request_id, payload, address):
        self.request_id = request_id
        self.payload = payload
        self.address = address
        self.event = threading.Event()
        self.response = None


class DocNode:
    def __init__(
        self,
        listen_host,
        port,
        allowed_user_ip,
        data_nodes,
        folder=DEFAULT_DOC_FOLDER,
        on_pending=None,
        on_log=None,
    ):
        self.listen_host = listen_host or "0.0.0.0"
        self.port = int(port)
        self.allowed_user_ip = (allowed_user_ip or "").strip()
        self.data_nodes = list(data_nodes)
        self.folder = folder
        self.local_ip = get_local_ip()
        self.node_id = f"doc:{self.local_ip}:{self.port}"
        self.on_pending = on_pending
        self.on_log = on_log

        self.stop_event = threading.Event()
        self.server_socket = None
        self.pending_lock = threading.Lock()
        self.active_pending = None
        self.approved_count = 0
        self.rejected_count = 0

    def log(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        if self.on_log:
            self.on_log(line)
        else:
            print(line)

    def start(self):
        os.makedirs(self.folder, exist_ok=True)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.listen_host, self.port))
        self.server_socket.listen(10)
        self.server_socket.settimeout(1.0)

        threading.Thread(target=self.accept_loop, daemon=True).start()

        self.log(f"Doc Node listening on {self.listen_host}:{self.port}")
        self.log(f"WiFi IP detected as {self.local_ip}")
        self.log(f"Allowed User Nodes: {self.allowed_user_ip or 'any'}")
        self.log(f"Data Nodes: {self.data_node_text()}")
        self.probe_data_nodes()

    def stop(self):
        self.stop_event.set()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def accept_loop(self):
        while not self.stop_event.is_set():
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(target=self.handle_client, args=(client, address), daemon=True).start()

    def handle_client(self, client, address):
        try:
            client.settimeout(10.0)
            packet = recv_packet(client)
            if not isinstance(packet, dict):
                send_packet(client, {"ok": False, "error": "packet must be a JSON object"})
                return

            packet_type = packet.get("type")
            if packet_type == "PING":
                response = {"ok": True, "type": "PONG", "node_id": self.node_id}
            elif packet_type == "USER_DATA":
                response = self.handle_user_data(packet, address)
            else:
                response = {"ok": False, "error": f"unknown packet type: {packet_type}"}

            send_packet(client, response)
        except Exception as exc:
            try:
                send_packet(client, {"ok": False, "error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    def handle_user_data(self, packet, address):
        if not self.user_allowed(address[0]):
            self.log(f"Rejected User Node {address[0]} because it is not the configured IP")
            return {"ok": False, "error": "this Doc Node is configured for another User Node"}

        payload = packet.get("payload")
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload must be an object"}

        if not str(payload.get("name", "")).strip() or not str(payload.get("problem", "")).strip():
            return {"ok": False, "error": "name and problem are required"}

        with self.pending_lock:
            if self.active_pending is not None:
                return {"ok": False, "error": "Doc Node is reviewing another User request"}
            pending = PendingRequest(
                sha256_text(canonical_json({"payload": payload, "time": now_utc()}))[:16],
                payload,
                address,
            )
            self.active_pending = pending

        self.log(f"Received User request {pending.request_id} from {address[0]}")
        if self.on_pending:
            self.on_pending(pending)

        if not pending.event.wait(PENDING_TIMEOUT_SECONDS):
            with self.pending_lock:
                if self.active_pending is pending:
                    self.active_pending = None
            self.log(f"Request {pending.request_id} timed out waiting for approval")
            return {"ok": False, "error": "Doc Node approval timed out"}

        with self.pending_lock:
            if self.active_pending is pending:
                self.active_pending = None

        return pending.response or {"ok": False, "error": "request closed without decision"}

    def user_allowed(self, ip):
        allowed = self.allowed_user_ip
        if not allowed or allowed in {"*", "any", "0.0.0.0"}:
            return True
        return ip == allowed

    def approve_pending(self, request_id, approved, note=""):
        with self.pending_lock:
            pending = self.active_pending
            if not pending or pending.request_id != request_id:
                return False, "pending request not found"

        if not approved:
            pending.response = {
                "ok": False,
                "type": "DOC_REJECTED",
                "request_id": pending.request_id,
                "error": note or "Doc Node rejected the request",
            }
            pending.event.set()
            self.rejected_count += 1
            self.log(f"Rejected request {pending.request_id}")
            return True, "rejected"

        document = self.build_document_record(pending.payload, pending.address, note)
        self.save_document(document)
        data_result = self.forward_to_data(document)

        if data_result["ok"]:
            self.approved_count += 1
            pending.response = {
                "ok": True,
                "type": "DOC_APPROVED",
                "request_id": pending.request_id,
                "doc_id": document["doc_id"],
                "content_hash": document["content_hash"],
                "block_index": data_result.get("block_index"),
                "block_hash": data_result.get("block_hash"),
                "data_nodes": data_result.get("data_nodes", []),
                "wallet_address": data_result.get("data_nodes", [{}])[0].get("wallet_address") if data_result.get("data_nodes") else "",
                "token_cost": data_result.get("data_nodes", [{}])[0].get("token_cost") if data_result.get("data_nodes") else None,
                "wallet_balance": data_result.get("data_nodes", [{}])[0].get("wallet_balance") if data_result.get("data_nodes") else None,
                "message": "Doc Node approved and Data Node stored the record",
            }
            self.log(f"Approved request {pending.request_id} as doc {document['doc_id']}")
        else:
            pending.response = {
                "ok": False,
                "type": "DOC_APPROVED_DATA_FAILED",
                "request_id": pending.request_id,
                "doc_id": document["doc_id"],
                "error": data_result.get("error", "all Data Nodes failed"),
            }
            self.log(f"Approved request {pending.request_id}, but Data Nodes failed")

        pending.event.set()
        return True, "approved"

    def build_document_record(self, payload, address, doctor_note):
        approved_at = now_utc()
        approved_unix = int(time.time())
        fields = {key: payload.get(key, "") for key, _label in FORM_KEYS}
        content_hash = sha256_text(canonical_json({key: payload.get(key, "") for key, _label in FORM_KEYS}))
        doc_seed = canonical_json(
            {
                "content_hash": content_hash,
                "approved_at": approved_at,
                "doc_node": self.node_id,
                "user": payload.get("user_node", ""),
            }
        )
        doc_id = sha256_text(doc_seed)[:24]
        signature_material = canonical_json(
            {
                "doc_id": doc_id,
                "content_hash": content_hash,
                "doctor_note": doctor_note,
                "doc_node": self.node_id,
                "approved_unix": approved_unix,
            }
        )

        return {
            "doc_id": doc_id,
            "status": "approved_by_doc_node",
            "doc_node": self.node_id,
            "doc_node_ip": self.local_ip,
            "source_user_ip": address[0],
            "source_user_node": payload.get("user_node", f"user:{address[0]}"),
            "received_sent_at": payload.get("sent_at", ""),
            "approved_at": approved_at,
            "approved_unix": approved_unix,
            "doctor_note": doctor_note,
            "doc_signature": sha512_text(signature_material),
            "content_hash": content_hash,
            "wallet_name": payload.get("wallet_name", ""),
            "wallet_address": payload.get("wallet_address", ""),
            "token_cost": int(payload.get("token_cost", token_cost_for_fields(fields))),
            "fields": fields,
        }

    def save_document(self, document):
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, f"{document['doc_id']}.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(document, file, indent=2, sort_keys=True)
            file.write("\n")

    def forward_to_data(self, document):
        if not self.data_nodes:
            return {"ok": False, "error": "no Data Nodes configured"}

        successes = []
        errors = []
        data_nodes = list(self.data_nodes)
        random.shuffle(data_nodes)
        self.log(f"Random Data Node order: {self.data_node_text(data_nodes)}")

        for host, port in data_nodes:
            try:
                response = request(
                    host,
                    port,
                    {
                        "type": "DOC_SUBMIT",
                        "from": self.node_id,
                        "host": self.local_ip,
                        "port": self.port,
                        "document": document,
                    },
                    timeout=12.0,
                )
                if response and response.get("ok"):
                    item = {
                        "endpoint": f"{host}:{port}",
                        "block_index": response.get("block_index"),
                        "block_hash": response.get("block_hash"),
                        "wallet_address": response.get("wallet_address"),
                        "token_cost": response.get("token_cost"),
                        "wallet_balance": response.get("wallet_balance"),
                    }
                    successes.append(item)
                    self.log(f"Data Node {host}:{port} stored doc {document['doc_id']}")
                    break
                else:
                    error = response.get("error", "rejected") if response else "no response"
                    errors.append(f"{host}:{port} -> {error}")
            except Exception as exc:
                errors.append(f"{host}:{port} -> {exc}")

        if successes:
            first = successes[0]
            return {
                "ok": True,
                "data_nodes": successes,
                "block_index": first["block_index"],
                "block_hash": first["block_hash"],
            }
        return {"ok": False, "error": "; ".join(errors) if errors else "all Data Nodes failed"}

    def probe_data_nodes(self):
        for host, port in self.data_nodes:
            threading.Thread(target=self._probe_one_data_node, args=(host, port), daemon=True).start()

    def _probe_one_data_node(self, host, port):
        try:
            response = request(host, port, {"type": "PING", "from": self.node_id}, timeout=3.0)
            if response and response.get("ok"):
                self.log(f"Connected to Data Node {host}:{port}")
            else:
                self.log(f"Data Node {host}:{port} did not answer correctly")
        except Exception as exc:
            self.log(f"Data Node {host}:{port} is not reachable yet: {exc}")

    def data_node_text(self, data_nodes=None):
        data_nodes = self.data_nodes if data_nodes is None else data_nodes
        if not data_nodes:
            return "none"
        return ", ".join(f"{host}:{port}" for host, port in data_nodes)


class DocNodeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FerroFy Doc Node")
        self.root.geometry("1120x800")
        self.root.minsize(980, 720)
        install_dark_theme(root)

        self.node = None
        self.data_entries = []
        self.current_pending = None
        self.field_widgets = {}
        self.metric_labels = {}

        self._build_config()
        self._build_review()
        self.review_frame.grid_remove()

    def _build_config(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.config_frame = ttk.Frame(self.root, style="TFrame")
        self.config_frame.grid(row=0, column=0, sticky="nsew")
        self.config_frame.columnconfigure(0, weight=1)
        self.config_frame.rowconfigure(1, weight=1)

        header = BlockchainHeader(
            self.config_frame,
            "FERROFY DOC NODE",
            f"LOCAL IP {get_local_ip()}  /  USER PORT {DEFAULT_DOC_PORT}  /  DATA PORT {DEFAULT_DATA_PORT}",
        )
        header.grid(row=0, column=0, sticky="ew")

        shell = ttk.Frame(self.config_frame, padding=18, style="TFrame")
        shell.grid(row=1, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        network = make_panel(shell, padding=18)
        network.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        network.columnconfigure(1, weight=1)

        ttk.Label(network, text="CONNECTION ROUTES", style="PanelAccent.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Separator(network).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 14))

        self._info_row(network, 2, "User connects to", f"this machine on port {DEFAULT_DOC_PORT}")
        self._info_row(network, 3, "Doc listens on", "all local network interfaces")
        self._info_row(network, 4, "Allowed users", "any User Node on this local network")

        ttk.Label(network, text="Data Node Count", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=7)
        count_row = ttk.Frame(network, style="Panel.TFrame")
        count_row.grid(row=5, column=1, sticky="ew", pady=7)
        self.data_count = ttk.Entry(count_row, width=8)
        self.data_count.insert(0, "1")
        self.data_count.pack(side="left")
        ttk.Button(count_row, text="BUILD", command=self.build_data_inputs).pack(side="left", padx=8)
        ttk.Label(network, text=f"(Each On Port {DEFAULT_DATA_PORT})", style="PanelMuted.TLabel").grid(row=6, column=1, sticky="w", pady=2)

        data_panel = make_panel(shell, padding=18, style="Panel2.TFrame")
        data_panel.grid(row=0, column=1, sticky="nsew")
        data_panel.columnconfigure(0, weight=1)
        data_panel.rowconfigure(2, weight=1)

        ttk.Label(data_panel, text=f"DATA NODE IPs  (ALL PORT {DEFAULT_DATA_PORT})", style="PanelAccent.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(data_panel).grid(row=1, column=0, sticky="ew", pady=(10, 14))
        self.data_inputs_frame = ttk.Frame(data_panel, style="Panel2.TFrame")
        self.data_inputs_frame.grid(row=2, column=0, sticky="nsew")
        self.data_inputs_frame.columnconfigure(1, weight=1)
        self.build_data_inputs()

        footer = ttk.Frame(data_panel, style="Panel2.TFrame")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Button(footer, text="START DOC NODE", style="Accent.TButton", command=self.start_node).grid(row=0, column=1)

    def _entry_row(self, parent, row, label, value):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 10))
        entry = ttk.Entry(parent)
        entry.insert(0, value)
        entry.grid(row=row, column=1, sticky="ew", pady=7)
        return entry

    def _info_row(self, parent, row, label, value):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 10))
        ttk.Label(parent, text=value, style="PanelMuted.TLabel").grid(row=row, column=1, sticky="w", pady=7)

    def build_data_inputs(self):
        for child in self.data_inputs_frame.winfo_children():
            child.destroy()
        self.data_entries = []

        try:
            count = max(0, int(self.data_count.get().strip() or "0"))
        except ValueError:
            count = 1
            self.data_count.delete(0, "end")
            self.data_count.insert(0, "1")

        for index in range(count):
            ttk.Label(self.data_inputs_frame, text=f"Data Node {index + 1}", style="Panel2.TLabel").grid(
                row=index, column=0, sticky="w", pady=7, padx=(0, 12)
            )
            entry = ttk.Entry(self.data_inputs_frame)
            entry.insert(0, "127.0.0.1")
            entry.grid(row=index, column=1, sticky="ew", pady=7)
            self.data_entries.append(entry)

    def _build_review(self):
        self.review_frame = ttk.Frame(self.root, style="TFrame")
        self.review_frame.grid(row=0, column=0, sticky="nsew")
        self.review_frame.columnconfigure(0, weight=1)
        self.review_frame.rowconfigure(1, weight=1)

        header = BlockchainHeader(
            self.review_frame,
            "FERROFY DOC NODE",
            "LIVE REVIEW  /  APPROVE TO BLOCKCHAIN  /  REJECT TO USER",
        )
        header.grid(row=0, column=0, sticky="ew")

        shell = ttk.Frame(self.review_frame, padding=18, style="TFrame")
        shell.grid(row=1, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=3)
        shell.columnconfigure(1, weight=2)
        shell.rowconfigure(0, weight=1)

        case_container, case_panel = make_scrolled_frame(shell, padding=18, style="Panel2.TFrame")
        case_container.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        case_panel.columnconfigure(1, weight=1)
        case_panel.rowconfigure(3, weight=1)
        case_panel.rowconfigure(4, weight=1)
        case_panel.rowconfigure(6, weight=1)
        case_panel.rowconfigure(7, weight=1)

        top = ttk.Frame(case_panel, style="Panel2.TFrame")
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="PENDING CASE REVIEW", style="PanelAccent.TLabel").grid(row=0, column=0, sticky="w")
        self.review_status = ttk.Label(top, text="WAITING", style="PanelMuted.TLabel")
        self.review_status.grid(row=0, column=1, sticky="e")
        ttk.Separator(case_panel).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 12))

        row = 2
        for key, label in FORM_KEYS:
            ttk.Label(case_panel, text=label, style="Panel2.TLabel").grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=5)
            h = 2 if key in {"name", "disease", "date"} else 3
            container, text = make_scrolled_text(case_panel, height=h, readonly=True)
            container.grid(row=row, column=1, sticky="nsew", pady=5)
            self.field_widgets[key] = text
            row += 1

        ttk.Label(case_panel, text="Doctor Note", style="Panel2.TLabel").grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=5)
        note_container, self.note = make_scrolled_text(case_panel, height=4)
        note_container.grid(row=row, column=1, sticky="nsew", pady=5)

        action_bar = ttk.Frame(case_panel, style="Panel2.TFrame")
        action_bar.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        action_bar.columnconfigure(0, weight=1)
        self.reject_button = ttk.Button(action_bar, text="NO / REJECT", style="Danger.TButton", command=lambda: self.decide(False), state="disabled")
        self.reject_button.grid(row=0, column=1, padx=8)
        self.approve_button = ttk.Button(action_bar, text="YES / APPROVE", style="Success.TButton", command=lambda: self.decide(True), state="disabled")
        self.approve_button.grid(row=0, column=2)

        side = make_panel(shell, padding=18)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(5, weight=1)

        ttk.Label(side, text="NODE STATE", style="PanelAccent.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Separator(side).grid(row=1, column=0, sticky="ew", pady=(10, 14))

        self._metric(side, 2, "APPROVED", "0", "approved")
        self._metric(side, 3, "REJECTED", "0", "rejected")
        self._metric(side, 4, "DATA ROUTES", "0", "routes")

        ttk.Label(side, text="EVENT LOG", style="PanelAccent.TLabel").grid(row=5, column=0, sticky="sw", pady=(18, 8))
        log_container, self.log_box = make_scrolled_text(side, height=18, readonly=True, font=("Consolas", 9))
        log_container.grid(row=6, column=0, sticky="nsew")
        side.rowconfigure(6, weight=1)

        bottom = ttk.Frame(side, style="Panel.TFrame")
        bottom.grid(row=7, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="STOP NODE", command=self.stop_node).grid(row=0, column=1)

    def _metric(self, parent, row, label, value, key):
        box = tk.Frame(parent, bg=COLORS["panel_2"], highlightthickness=1, highlightbackground=COLORS["line"])
        box.grid(row=row, column=0, sticky="ew", pady=5)
        box.columnconfigure(1, weight=1)
        tk.Label(box, text=label, bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=10
        )
        value_label = tk.Label(box, text=value, bg=COLORS["panel_2"], fg=COLORS["accent"], font=("Consolas", 13, "bold"))
        value_label.grid(row=0, column=1, sticky="e", padx=12, pady=10)
        self.metric_labels[key] = value_label

    def start_node(self):
        try:
            data_nodes = [parse_fixed_endpoint(entry.get().strip(), DEFAULT_DATA_PORT, "Data Node") for entry in self.data_entries]
        except Exception as exc:
            messagebox.showerror("Invalid Setup", str(exc))
            return

        self.node = DocNode(
            listen_host=DEFAULT_LISTEN_HOST,
            port=DEFAULT_DOC_PORT,
            allowed_user_ip="",
            data_nodes=data_nodes,
            on_pending=lambda pending: self.root.after(0, self.show_pending, pending),
            on_log=lambda line: self.root.after(0, self.add_log, line),
        )

        try:
            self.node.start()
        except Exception as exc:
            messagebox.showerror("Start Failed", str(exc))
            return

        self.metric_labels["routes"].configure(text=str(len(data_nodes)))
        self.config_frame.grid_remove()
        self.review_frame.grid()
        self.add_log("Doc GUI online.")

    def stop_node(self):
        if self.node:
            self.node.stop()
        self.root.destroy()

    def show_pending(self, pending):
        self.current_pending = pending
        self.review_status.configure(text=f"REQUEST {pending.request_id}", foreground=status_color("warn"))
        for key, _label in FORM_KEYS:
            set_text_value(self.field_widgets[key], str(pending.payload.get(key, "")))
        self.note.delete("1.0", "end")
        self.approve_button.configure(state="normal")
        self.reject_button.configure(state="normal")
        self.add_log(f"Case loaded from {pending.address[0]}.")

    def decide(self, approved):
        if not self.current_pending or not self.node:
            return
        pending = self.current_pending
        note = self.note.get("1.0", "end").strip()
        self.approve_button.configure(state="disabled")
        self.reject_button.configure(state="disabled")
        self.review_status.configure(text="COMMITTING DECISION", foreground=status_color("warn"))

        threading.Thread(target=self._decision_worker, args=(pending, approved, note), daemon=True).start()

    def _decision_worker(self, pending, approved, note):
        ok, message = self.node.approve_pending(pending.request_id, approved, note)
        self.root.after(0, lambda: self.finish_decision(ok, message))

    def finish_decision(self, ok, message):
        self.current_pending = None
        self.review_status.configure(
            text=f"DONE: {message}".upper() if ok else f"FAILED: {message}".upper(),
            foreground=status_color("ok" if ok else "error"),
        )
        for key, _label in FORM_KEYS:
            set_text_value(self.field_widgets[key], "")
        self.note.delete("1.0", "end")
        if self.node:
            self.metric_labels["approved"].configure(text=str(self.node.approved_count))
            self.metric_labels["rejected"].configure(text=str(self.node.rejected_count))

    def add_log(self, line):
        append_log(self.log_box, line)


def Start_Doc():
    root = tk.Tk()
    app = DocNodeApp(root)
    root.protocol("WM_DELETE_WINDOW", app.stop_node)
    root.mainloop()


if __name__ == "__main__":
    Start_Doc()
