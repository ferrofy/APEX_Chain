import os
import socket
import threading
import time

from Blockchain import (
    DEFAULT_DIFFICULTY,
    chain_signature,
    chain_summary,
    create_genesis_block,
    create_next_block,
    first_invalid_block,
    load_chain,
    save_block,
    save_chain,
    select_consensus_chain,
    validate_block,
    validate_chain,
)
from Protocol import (
    get_local_ip,
    now_utc,
    parse_peer_list,
    recv_packet,
    request,
    send_packet,
)

HOST = "0.0.0.0"
DEFAULT_DATA_PORT = 5200
DEFAULT_BLOCK_ROOT = "Blocks"


def ask_int(label, default):
    raw = input(f"{label} [{default}] > ").strip()
    if not raw:
        return int(default)
    return int(raw)


class DataNode:
    def __init__(self, port, peers=None, folder=None, difficulty=DEFAULT_DIFFICULTY):
        self.port = int(port)
        self.host = HOST
        self.local_ip = get_local_ip()
        self.node_id = f"data:{self.local_ip}:{self.port}"
        self.folder = folder or os.path.join(DEFAULT_BLOCK_ROOT, f"DataNode_{self.port}")
        self.difficulty = int(difficulty)

        self.chain = []
        self.peers = set(peers or [])
        self.chain_lock = threading.Lock()
        self.peers_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.server_socket = None

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def start(self):
        self.load_or_create_chain()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(20)
        self.server_socket.settimeout(1.0)

        threading.Thread(target=self.accept_loop, daemon=True).start()
        threading.Thread(target=self.maintenance_loop, daemon=True).start()

        self.log(f"Data Node running at {self.local_ip}:{self.port}")
        self.log(f"Block folder: {self.folder}")
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
            genesis = create_genesis_block(self.node_id, self.difficulty)
            self.chain = [genesis]
            save_chain(self.folder, self.chain)
            self.log("Created genesis block")
            return

        self.chain = loaded
        ok, reason = validate_chain(self.chain)
        if ok:
            self.log(f"Loaded {len(self.chain)} block(s)")
        else:
            index, bad_reason = first_invalid_block(self.chain)
            self.log(f"Local chain is invalid at block {index}: {bad_reason}")
            self.log("It will be repaired from peers when a valid peer chain is available")

    def accept_loop(self):
        while not self.stop_event.is_set():
            try:
                client, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=self.handle_client,
                args=(client, address),
                daemon=True,
            ).start()

    def maintenance_loop(self):
        while not self.stop_event.is_set():
            time.sleep(15)
            with self.chain_lock:
                local_chain = list(self.chain)
            ok, reason = validate_chain(local_chain)
            if not ok:
                self.log(f"Detected bad local block: {reason}")
                self.repair_from_peers("automatic integrity check")

    def handle_client(self, client, address):
        try:
            packet = recv_packet(client)
            if not isinstance(packet, dict):
                send_packet(client, {"ok": False, "error": "packet must be a JSON object"})
                return

            packet_type = packet.get("type")
            if packet_type == "HELLO_PEER":
                response = self.handle_hello(packet, address)
            elif packet_type == "GET_CHAIN":
                response = self.handle_get_chain()
            elif packet_type == "DOC_SUBMIT":
                response = self.handle_doc_submit(packet, address)
            elif packet_type == "BLOCK_PROPOSE":
                response = self.handle_block_proposal(packet, address)
            elif packet_type == "PING":
                response = {"ok": True, "type": "PONG", "node_id": self.node_id}
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

    def handle_hello(self, packet, address):
        peer_port = int(packet.get("port", DEFAULT_DATA_PORT))
        peer_host = packet.get("host") or address[0]
        self.add_peer(peer_host, peer_port)
        return {
            "ok": True,
            "type": "HELLO_PEER_ACK",
            "node_id": self.node_id,
            "host": self.local_ip,
            "port": self.port,
            "summary": self.current_summary(),
            "peers": self.peer_list(),
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
        document = packet.get("document")
        if not isinstance(document, dict):
            return {"ok": False, "error": "document must be an object"}

        ok, reason = self.ensure_valid_chain()
        if not ok:
            return {"ok": False, "error": f"local chain is not repairable yet: {reason}"}

        data = {
            "kind": "document_record",
            "received_from": packet.get("from", f"doc:{address[0]}"),
            "accepted_at": now_utc(),
            "document": document,
        }

        with self.chain_lock:
            block = create_next_block(self.chain[-1], data, self.node_id, self.difficulty)
            self.chain.append(block)
            save_block(self.folder, block)

        self.log(f"Mined block {block['index']} for doc {document.get('doc_id', 'unknown')}")
        self.broadcast_block(block)
        return {
            "ok": True,
            "type": "DATA_ACK",
            "node_id": self.node_id,
            "block_index": block["index"],
            "block_hash": block["hash"],
            "stored_at": now_utc(),
        }

    def handle_block_proposal(self, packet, address):
        block = packet.get("block")
        peer_port = int(packet.get("port", DEFAULT_DATA_PORT))
        peer_host = packet.get("host") or address[0]
        self.add_peer(peer_host, peer_port)

        if not isinstance(block, dict):
            return {"ok": False, "accepted": False, "error": "block must be an object"}

        chain_ok, chain_reason = self.ensure_valid_chain()
        if not chain_ok:
            return {
                "ok": False,
                "accepted": False,
                "error": f"local chain is not repairable yet: {chain_reason}",
            }

        needs_repair = False
        accepted = False
        reason = "duplicate block"

        with self.chain_lock:
            local_len = len(self.chain)
            block_index = int(block.get("index", -1))

            if block_index < local_len:
                if self.chain[block_index].get("hash") == block.get("hash"):
                    accepted = True
                    reason = "already have block"
                else:
                    needs_repair = True
                    reason = f"conflict at block {block_index}"
            elif block_index == local_len:
                previous = self.chain[-1] if self.chain else None
                ok, validate_reason = validate_block(block, previous)
                if ok:
                    self.chain.append(block)
                    save_block(self.folder, block)
                    accepted = True
                    reason = f"accepted block {block_index}"
                else:
                    needs_repair = True
                    reason = validate_reason
            else:
                needs_repair = True
                reason = f"missing block(s) before {block_index}"

        if needs_repair:
            self.log(f"Peer block rejected: {reason}. Asking peers for repair.")
            self.repair_from_peers("peer block conflict")

        return {
            "ok": accepted,
            "accepted": accepted,
            "reason": reason,
            "summary": self.current_summary(),
        }

    def ensure_valid_chain(self):
        with self.chain_lock:
            local_chain = list(self.chain)
        ok, reason = validate_chain(local_chain)
        if ok:
            return True, reason

        self.log(f"Local chain failed validation: {reason}")
        repaired = self.repair_from_peers("write blocked by invalid chain")
        if not repaired:
            return False, reason

        with self.chain_lock:
            return validate_chain(self.chain)

    def add_peer(self, host, port):
        port = int(port)
        if port == self.port and host in {self.local_ip, "127.0.0.1", "localhost", "0.0.0.0"}:
            return
        with self.peers_lock:
            self.peers.add((host, port))

    def peer_list(self):
        with self.peers_lock:
            return [{"host": host, "port": port} for host, port in sorted(self.peers)]

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
                        "host": self.local_ip,
                        "port": self.port,
                    },
                    timeout=4.0,
                )
                if response and response.get("ok"):
                    for peer in response.get("peers", []):
                        self.add_peer(peer["host"], int(peer["port"]))
                    self.log(f"Connected with peer {host}:{port}")
            except Exception as exc:
                self.log(f"Peer {host}:{port} unavailable: {exc}")

    def peer_tuples(self):
        with self.peers_lock:
            return sorted(self.peers)

    def fetch_peer_chain(self, host, port):
        response = request(
            host,
            port,
            {
                "type": "GET_CHAIN",
                "from": self.node_id,
                "host": self.local_ip,
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
                peer_chain = self.fetch_peer_chain(host, port)
                candidates.append((f"{host}:{port}", peer_chain))
                peer_count += 1
            except Exception as exc:
                self.log(f"Could not read chain from {host}:{port}: {exc}")

        if peer_count == 0:
            with self.chain_lock:
                ok, local_reason = validate_chain(self.chain)
            if ok:
                return True
            self.log(f"No peer chain available for repair ({reason})")
            return False

        selected, select_reason = select_consensus_chain(candidates)
        if selected is None:
            self.log(f"Repair failed: {select_reason}")
            return False

        with self.chain_lock:
            local_ok, _local_reason = validate_chain(self.chain)
            local_signature = chain_signature(self.chain)
            selected_signature = chain_signature(selected)
            should_replace = (
                not local_ok
                or (selected_signature != local_signature and len(selected) >= len(self.chain))
            )
            if should_replace:
                self.chain = selected
                save_chain(self.folder, self.chain)
                self.log(f"Chain repaired from peers ({select_reason})")
                return True

        return True

    def broadcast_block(self, block):
        for host, port in self.peer_tuples():
            threading.Thread(
                target=self.send_block_to_peer,
                args=(host, port, block),
                daemon=True,
            ).start()

    def send_block_to_peer(self, host, port, block):
        try:
            response = request(
                host,
                port,
                {
                    "type": "BLOCK_PROPOSE",
                    "from": self.node_id,
                    "host": self.local_ip,
                    "port": self.port,
                    "block": block,
                },
                timeout=6.0,
            )
            if not response or not response.get("accepted"):
                reason = response.get("reason", "not accepted") if response else "no response"
                self.log(f"Peer {host}:{port} did not accept block {block['index']}: {reason}")
        except Exception as exc:
            self.log(f"Broadcast to {host}:{port} failed: {exc}")

    def print_status(self):
        summary = self.current_summary()
        print()
        print(f"Node      : {self.node_id}")
        print(f"Folder    : {self.folder}")
        print(f"Peers     : {len(self.peer_tuples())}")
        print(f"Blocks    : {summary['length']}")
        print(f"Valid     : {summary['valid']} ({summary['reason']})")
        print(f"Tip hash  : {summary['tip_hash'][:24]}...")

    def print_peers(self):
        peers = self.peer_tuples()
        if not peers:
            print("No peers connected.")
            return
        for host, port in peers:
            print(f"- {host}:{port}")

    def print_chain(self):
        with self.chain_lock:
            visible = list(self.chain)
        for block in visible:
            data = block.get("data", {})
            kind = data.get("kind", "unknown")
            doc = data.get("document", {})
            label = doc.get("title") or doc.get("doc_id") or kind
            print(f"#{block['index']:03d} {block['hash'][:18]}... {label}")


def Start_Data():
    print()
    print("FerroFy Data Node")
    print("This node stores blocks and repairs bad local blocks from peer consensus.")
    print()

    port = ask_int("Data node port", DEFAULT_DATA_PORT)
    peer_raw = input("Peer data nodes (comma host:port, blank for none) > ").strip()
    peers = parse_peer_list(peer_raw, DEFAULT_DATA_PORT) if peer_raw else []
    folder_default = os.path.join(DEFAULT_BLOCK_ROOT, f"DataNode_{port}")
    folder = input(f"Block folder [{folder_default}] > ").strip() or folder_default

    node = DataNode(port=port, peers=peers, folder=folder)
    node.start()

    print()
    print("Commands: status, peers, chain, repair, quit")
    try:
        while True:
            command = input("data> ").strip().lower()
            if command in {"q", "quit", "exit"}:
                break
            if command in {"", "status"}:
                node.print_status()
            elif command == "peers":
                node.print_peers()
            elif command == "chain":
                node.print_chain()
            elif command == "repair":
                node.repair_from_peers("manual command")
                node.print_status()
            else:
                print("Unknown command. Use: status, peers, chain, repair, quit")
    except KeyboardInterrupt:
        print()
    finally:
        node.stop()
        print("Data node stopped.")


if __name__ == "__main__":
    Start_Data()
