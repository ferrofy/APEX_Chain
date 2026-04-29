import os
import socket
import threading
import time

from Blockchain import (
    append_record_to_block,
    block_is_open,
    block_hash,
    block_messages,
    block_number,
    block_previous_hash,
    build_medical_record,
    chain_signature,
    chain_summary,
    create_next_block,
    derive_wallet_address,
    first_invalid_block,
    load_chain,
    save_block,
    save_chain,
    select_consensus_chain,
    token_cost_for_fields,
    validate_block,
    validate_chain,
    wallet_balance_from_chain,
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
DEFAULT_BLOCK_ROOT = os.path.join(PROJECT_ROOT, "Blocks")


def ask_int(label, default):
    raw = input(f"{label} [{default}] > ").strip()
    if not raw:
        return int(default)
    return int(raw)


def ask_endpoints(label, default_port):
    count = ask_int(f"How many {label}s to connect", 0)
    endpoints = []
    for index in range(count):
        while True:
            raw = input(f"{label} {index + 1} IP / host [port {default_port}] > ").strip()
            try:
                endpoints.append(parse_fixed_endpoint(raw, default_port, label))
                break
            except Exception as exc:
                print(f"Invalid address: {exc}")
    return endpoints


class DataNode:
    def __init__(self, listen_host, port, doc_nodes=None, data_peers=None, folder=None):
        self.listen_host = listen_host or "0.0.0.0"
        self.port = int(port)
        self.doc_nodes = list(doc_nodes or [])
        self.data_peers = set(data_peers or [])
        self.folder = folder or DEFAULT_BLOCK_ROOT
        self.local_ip = get_local_ip()
        self.node_id = f"data:{self.local_ip}:{self.port}"

        self.chain = []
        self.chain_lock = threading.Lock()
        self.peer_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.server_socket = None

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def start(self):
        self.load_or_create_chain()

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.listen_host, self.port))
        self.server_socket.listen(30)
        self.server_socket.settimeout(1.0)

        threading.Thread(target=self.accept_loop, daemon=True).start()
        threading.Thread(target=self.maintenance_loop, daemon=True).start()

        self.log(f"Data Node listening on {self.listen_host}:{self.port}")
        self.log(f"WiFi IP detected as {self.local_ip}")
        self.log(f"Block folder: {self.folder}")
        self.log(f"Allowed Doc Nodes: {self.endpoint_text(self.doc_nodes, empty='any')}")
        self.log(f"Data Peers: {self.endpoint_text(self.peer_tuples())}")

        self.probe_doc_nodes()
        self.announce_to_peers()
        self.repair_from_peers("startup")

    def stop(self):
        self.stop_event.set()
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def load_or_create_chain(self):
        loaded = load_chain(self.folder)
        if not loaded:
            self.chain = []
            os.makedirs(self.folder, exist_ok=True)
            self.log("Ready to mine Block_1 when the first Doc record arrives")
            return

        self.chain = loaded
        ok, reason = validate_chain(self.chain)
        if ok:
            self.log(f"Loaded {len(self.chain)} block(s)")
        else:
            index, bad_reason = first_invalid_block(self.chain)
            self.log(f"Local chain is invalid at block {index}: {bad_reason}")
            self.log("It will be repaired from Data peers if a valid majority is available")

    def accept_loop(self):
        while not self.stop_event.is_set():
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(target=self.handle_client, args=(client, address), daemon=True).start()

    def maintenance_loop(self):
        while not self.stop_event.is_set():
            time.sleep(15)
            with self.chain_lock:
                local_chain = list(self.chain)
            ok, reason = validate_chain(local_chain)
            if not ok:
                self.log(f"Local chain failed validation: {reason}")
                self.repair_from_peers("automatic validation")

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
            elif packet_type == "HELLO_PEER":
                response = self.handle_hello_peer(packet, address)
            elif packet_type == "GET_CHAIN":
                response = self.handle_get_chain()
            elif packet_type == "DOC_SUBMIT":
                response = self.handle_doc_submit(packet, address)
            elif packet_type == "BLOCK_PROPOSE":
                response = self.handle_block_proposal(packet, address)
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

    def handle_hello_peer(self, packet, address):
        host = packet.get("host") or address[0]
        port = int(packet.get("port", DEFAULT_DATA_PORT))
        self.add_peer(host, port)
        return {
            "ok": True,
            "type": "HELLO_PEER_ACK",
            "node_id": self.node_id,
            "host": self.advertised_host(),
            "port": self.port,
            "peers": [{"host": host, "port": port} for host, port in self.peer_tuples()],
            "summary": self.current_summary(),
        }

    def handle_get_chain(self):
        with self.chain_lock:
            chain_copy = [dict(block) for block in self.chain]
        return {
            "ok": True,
            "type": "CHAIN_RESPONSE",
            "node_id": self.node_id,
            "chain": chain_copy,
            "summary": chain_summary(chain_copy),
        }

    def handle_doc_submit(self, packet, address):
        if not self.doc_allowed(address[0], packet.get("host", "")):
            self.log(f"Rejected Doc Node {address[0]} Because It Is Not Configured")
            return {"ok": False, "error": "Doc Node IP Is Not Allowed On This Data Node"}

        document = packet.get("document")
        if not isinstance(document, dict):
            return {"ok": False, "error": "Document Must Be An Object"}

        doc_id = document.get("doc_id")
        if not doc_id:
            return {"ok": False, "error": "Document Missing doc_id"}

        ok, reason = self.ensure_valid_chain()
        if not ok:
            return {"ok": False, "error": f"Local Chain Is Not Repairable Yet: {reason}"}

        existing = self.find_document_block(doc_id)
        if existing:
            self.log(f"Doc {doc_id} Already Exists At Block {block_number(existing)}")
            return {
                "ok": True,
                "type": "DATA_ACK",
                "node_id": self.node_id,
                "block_index": block_number(existing),
                "block_hash": block_hash(existing),
                "duplicate": True,
            }

        creator = packet.get("from", f"doc:{address[0]}")
        wallet_address = derive_wallet_address(document)
        token_cost = int(document.get("token_cost", token_cost_for_fields(document.get("fields", {}))))

        with self.chain_lock:
            balance_before = wallet_balance_from_chain(self.chain, wallet_address)
            if balance_before < token_cost:
                return {
                    "ok": False,
                    "error": f"wallet balance too low: needs {token_cost}, has {balance_before}",
                }

            record = build_medical_record(document, self.node_id, balance_before)
            last_block = self.chain[-1] if self.chain else None
            if last_block and block_is_open(last_block):
                block = append_record_to_block(last_block, record)
                self.chain[-1] = block
                save_block(self.folder, block)
                action = f"Appended Record To Block {block_number(block)}"
            else:
                block = create_next_block(last_block, [record], creator)
                self.chain.append(block)
                save_block(self.folder, block)
                action = f"Mined New Block {block_number(block)}"

        self.log(f"{action} For Doc {doc_id}")
        self.broadcast_block(block)
        self.repair_from_peers("new block verification")

        return {
            "ok": True,
            "type": "DATA_ACK",
            "node_id": self.node_id,
            "block_index": block_number(block),
            "block_hash": block_hash(block),
            "wallet_address": wallet_address,
            "token_cost": token_cost,
            "wallet_balance": balance_before - token_cost,
        }

    def handle_block_proposal(self, packet, address):
        peer_host = packet.get("host") or address[0]
        peer_port = int(packet.get("port", DEFAULT_DATA_PORT))
        self.add_peer(peer_host, peer_port)

        block = packet.get("block")
        if not isinstance(block, dict):
            return {"ok": False, "accepted": False, "error": "Block Must Be An Object"}

        ok, reason = self.ensure_valid_chain()
        if not ok:
            return {"ok": False, "accepted": False, "error": f"Local Chain Invalid: {reason}"}

        try:
            proposed_no = block_number(block)
        except Exception:
            return {"ok": False, "accepted": False, "error": "Block No must be an integer"}

        accepted = False
        reason = "not checked"
        needs_consensus = False

        with self.chain_lock:
            local_len = len(self.chain)
            expected_next = local_len + 1
            proposed_pos = proposed_no - 1

            if proposed_no <= local_len and proposed_pos >= 0:
                local_block = self.chain[proposed_pos]
                if block_hash(local_block) == block_hash(block):
                    accepted = True
                    reason = f"Already Have Same Block {proposed_no}"
                elif proposed_no == local_len and self.can_replace_open_block(local_block, block):
                    previous = self.chain[proposed_pos - 1] if proposed_pos > 0 else None
                    valid, validate_reason = validate_block(block, previous)
                    if valid:
                        self.chain[proposed_pos] = block
                        save_block(self.folder, block)
                        accepted = True
                        reason = f"Updated Open Block {proposed_no}"
                        self.log(f"Updated Open Block {proposed_no} From {peer_host}:{peer_port}")
                    else:
                        needs_consensus = True
                        reason = validate_reason
                else:
                    needs_consensus = True
                    reason = f"Conflict At Block {proposed_no}"
            elif proposed_no == expected_next:
                previous = self.chain[-1] if self.chain else None
                valid, validate_reason = validate_block(block, previous)
                if valid:
                    self.chain.append(block)
                    save_block(self.folder, block)
                    accepted = True
                    reason = f"Accepted Block {proposed_no}"
                    self.log(f"Accepted Block {proposed_no} From {peer_host}:{peer_port}")
                else:
                    needs_consensus = True
                    reason = validate_reason
            else:
                needs_consensus = True
                reason = f"Missing Block(s) Before {proposed_no}"

        if needs_consensus:
            self.log(f"Block Proposal Mismatch: {reason}. Asking Data Peers For Majority.")
            self.repair_from_peers("block proposal mismatch")

        return {
            "ok": accepted,
            "accepted": accepted,
            "reason": reason,
            "summary": self.current_summary(),
        }

    def can_replace_open_block(self, local_block, proposed_block):
        if block_number(local_block) != block_number(proposed_block):
            return False
        if block_previous_hash(proposed_block) != block_previous_hash(local_block):
            return False
        if not block_is_open(local_block):
            return False
        return len(block_messages(proposed_block)) > len(block_messages(local_block))

    def doc_allowed(self, remote_ip, packet_host):
        if not self.doc_nodes:
            return True
        allowed_hosts = {host for host, _port in self.doc_nodes}
        return remote_ip in allowed_hosts or packet_host in allowed_hosts

    def ensure_valid_chain(self):
        with self.chain_lock:
            local_chain = list(self.chain)
        ok, reason = validate_chain(local_chain)
        if ok:
            return True, reason

        self.log(f"Local chain is invalid: {reason}")
        if not self.repair_from_peers("invalid local chain"):
            return False, reason
        with self.chain_lock:
            return validate_chain(self.chain)

    def find_document_block(self, doc_id):
        with self.chain_lock:
            for block in self.chain:
                for record in block_messages(block):
                    if record.get("Transaction Id") == doc_id or record.get("Doc_Id") == doc_id:
                        return dict(block)
        return None

    def add_peer(self, host, port):
        port = int(port)
        if port == self.port and host in {self.listen_host, self.local_ip, "127.0.0.1", "localhost", "0.0.0.0"}:
            return
        with self.peer_lock:
            self.data_peers.add((host, port))

    def peer_tuples(self):
        with self.peer_lock:
            return sorted(self.data_peers)

    def current_summary(self):
        with self.chain_lock:
            return chain_summary(list(self.chain))

    def announce_to_peers(self):
        for host, port in self.peer_tuples():
            try:
                response = request(
                    host,
                    port,
                    {
                        "type": "HELLO_PEER",
                        "from": self.node_id,
                        "host": self.advertised_host(),
                        "port": self.port,
                    },
                    timeout=4.0,
                )
                if response and response.get("ok"):
                    for peer in response.get("peers", []):
                        self.add_peer(peer["host"], int(peer["port"]))
                    self.log(f"Connected to Data peer {host}:{port}")
            except Exception as exc:
                self.log(f"Data peer {host}:{port} not reachable yet: {exc}")

    def probe_doc_nodes(self):
        for host, port in self.doc_nodes:
            threading.Thread(target=self._probe_doc_node, args=(host, port), daemon=True).start()

    def _probe_doc_node(self, host, port):
        try:
            response = request(host, port, {"type": "PING", "from": self.node_id}, timeout=3.0)
            if response and response.get("ok"):
                self.log(f"Doc Node {host}:{port} is reachable")
            else:
                self.log(f"Doc Node {host}:{port} did not answer correctly")
        except Exception as exc:
            self.log(f"Doc Node {host}:{port} is not reachable yet: {exc}")

    def fetch_peer_chain(self, host, port):
        response = request(
            host,
            port,
            {
                "type": "GET_CHAIN",
                "from": self.node_id,
                "host": self.advertised_host(),
                "port": self.port,
            },
            timeout=6.0,
        )
        if not response or not response.get("ok"):
            raise RuntimeError(response.get("error", "peer did not return ok") if response else "no response")
        chain = response.get("chain")
        if not isinstance(chain, list):
            raise RuntimeError("peer chain response is not a list")
        return chain

    def repair_from_peers(self, reason):
        candidates = []
        with self.chain_lock:
            candidates.append((f"local:{self.port}", [dict(block) for block in self.chain]))

        peer_count = 0
        for host, port in self.peer_tuples():
            try:
                candidates.append((f"{host}:{port}", self.fetch_peer_chain(host, port)))
                peer_count += 1
            except Exception as exc:
                self.log(f"Could not read chain from {host}:{port}: {exc}")

        if peer_count == 0:
            with self.chain_lock:
                ok, _local_reason = validate_chain(self.chain)
            if not ok:
                self.log(f"No Data peer available for repair ({reason})")
            return ok

        selected, select_reason = select_consensus_chain(candidates)
        if selected is None:
            self.log(f"Consensus failed: {select_reason}")
            return False

        with self.chain_lock:
            local_ok, _local_reason = validate_chain(self.chain)
            local_signature = chain_signature(self.chain)
            selected_signature = chain_signature(selected)
            should_replace = (
                not local_ok
                or (
                    selected_signature != local_signature
                    and (select_reason.startswith("majority") or len(selected) >= len(self.chain))
                )
            )
            if should_replace:
                self.chain = selected
                save_chain(self.folder, self.chain)
                self.log(f"Chain repaired by Data peer consensus: {select_reason}")
                return True

        return True

    def broadcast_block(self, block):
        rejected = []
        for host, port in self.peer_tuples():
            try:
                response = request(
                    host,
                    port,
                    {
                        "type": "BLOCK_PROPOSE",
                        "from": self.node_id,
                        "host": self.advertised_host(),
                        "port": self.port,
                        "block": block,
                    },
                    timeout=6.0,
                )
                if response and response.get("accepted"):
                    self.log(f"Peer {host}:{port} confirmed Block_{block_number(block)}")
                else:
                    reason = response.get("reason", "not accepted") if response else "no response"
                    rejected.append(f"{host}:{port} -> {reason}")
            except Exception as exc:
                rejected.append(f"{host}:{port} -> {exc}")

        if rejected:
            self.log("Some peers disagreed: " + "; ".join(rejected))

    def endpoint_text(self, endpoints, empty="none"):
        if not endpoints:
            return empty
        return ", ".join(f"{host}:{port}" for host, port in endpoints)

    def advertised_host(self):
        if self.listen_host in {"", "0.0.0.0"}:
            return self.local_ip
        return self.listen_host

    def print_status(self):
        summary = self.current_summary()
        print()
        print(f"Node       : {self.node_id}")
        print(f"Listen     : {self.listen_host}:{self.port}")
        print(f"Folder     : {self.folder}")
        print(f"Doc Nodes  : {self.endpoint_text(self.doc_nodes, empty='any')}")
        print(f"Data Peers : {self.endpoint_text(self.peer_tuples())}")
        print(f"Blocks     : {summary['length']}")
        print(f"Messages   : {summary.get('messages', 0)}")
        print(f"Valid      : {summary['valid']} ({summary['reason']})")
        print(f"Tip Hash   : {summary['tip_hash'][:32]}...")

    def print_chain(self):
        with self.chain_lock:
            visible = list(self.chain)
        if not visible:
            print("No Blocks.")
            return
        for block in visible:
            records = block_messages(block)
            record_count = len(records)
            first_record = records[0] if records else {}
            label = first_record.get("Patient Name", "empty")
            open_status = "Open" if block_is_open(block) else "Sealed"
            print(f"Block_{block_number(block)}  {block_hash(block)[:20]}...  Records: {record_count}  [{open_status}]  {label}")


def Start_Data():
    print()
    print("=" * 72)
    print("FerroFy Data Node - Local WiFi Blockchain Storage")
    print("=" * 72)
    print(f"Detected WiFi IP: {get_local_ip()}")
    print(f"This Data Node listens on all local interfaces at fixed port {DEFAULT_DATA_PORT}.")
    print(f"User Nodes connect to Doc port {DEFAULT_DOC_PORT}; Doc Nodes submit to Data port {DEFAULT_DATA_PORT}.")
    print()

    listen_host = DEFAULT_LISTEN_HOST
    port = DEFAULT_DATA_PORT
    doc_nodes = []
    data_peers = ask_endpoints("Data Node peer", DEFAULT_DATA_PORT)

    folder_default = DEFAULT_BLOCK_ROOT
    folder = input(f"Block folder [{folder_default}] > ").strip() or folder_default

    node = DataNode(
        listen_host=listen_host,
        port=port,
        doc_nodes=doc_nodes,
        data_peers=data_peers,
        folder=folder,
    )
    node.start()

    print()
    print("Commands: status, chain, repair, peers, quit")
    try:
        while True:
            command = input("data> ").strip().lower()
            if command in {"q", "quit", "exit"}:
                break
            if command in {"", "status"}:
                node.print_status()
            elif command == "chain":
                node.print_chain()
            elif command == "repair":
                node.repair_from_peers("manual command")
                node.print_status()
            elif command == "peers":
                print("Data Peers:", node.endpoint_text(node.peer_tuples()))
                print("Doc Nodes :", node.endpoint_text(node.doc_nodes, empty="any"))
            else:
                print("Unknown command. Use: status, chain, repair, peers, quit")
    except KeyboardInterrupt:
        print()
    finally:
        node.stop()
        print("Data node stopped.")


if __name__ == "__main__":
    Start_Data()
