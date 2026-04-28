import json
import os
import socket
import threading
import time

from Blockchain import canonical_json, sha256_text
from Protocol import (
    get_local_ip,
    now_utc,
    parse_peer_list,
    recv_packet,
    request,
    send_packet,
)

HOST = "0.0.0.0"
DEFAULT_DOC_PORT = 5100
DEFAULT_DATA_PORT = 5200
DEFAULT_DOC_FOLDER = os.path.join("Files", "Documents")


def ask_int(label, default):
    raw = input(f"{label} [{default}] > ").strip()
    if not raw:
        return int(default)
    return int(raw)


class DocNode:
    def __init__(self, port, data_nodes, folder=DEFAULT_DOC_FOLDER):
        self.port = int(port)
        self.data_nodes = list(data_nodes)
        self.folder = folder
        self.local_ip = get_local_ip()
        self.node_id = f"doc:{self.local_ip}:{self.port}"
        self.stop_event = threading.Event()
        self.server_socket = None
        self.doc_count = 0
        self.doc_lock = threading.Lock()

    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def start(self):
        os.makedirs(self.folder, exist_ok=True)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, self.port))
        self.server_socket.listen(20)
        self.server_socket.settimeout(1.0)

        threading.Thread(target=self.accept_loop, daemon=True).start()

        self.log(f"Doc Node running at {self.local_ip}:{self.port}")
        self.log(f"Forwarding verified documents to: {self.data_node_text()}")

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

            threading.Thread(
                target=self.handle_client,
                args=(client, address),
                daemon=True,
            ).start()

    def handle_client(self, client, address):
        try:
            packet = recv_packet(client)
            if not isinstance(packet, dict):
                send_packet(client, {"ok": False, "error": "packet must be a JSON object"})
                return

            packet_type = packet.get("type")
            if packet_type == "USER_DATA":
                response = self.handle_user_data(packet, address)
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

    def handle_user_data(self, packet, address):
        payload = packet.get("payload")
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload must be an object"}

        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not content:
            return {"ok": False, "error": "content cannot be empty"}

        document = self.build_document_record(payload, address)
        self.save_document(document)

        data_response = self.forward_to_data(document)
        if not data_response.get("ok"):
            return {
                "ok": False,
                "type": "DOC_ACK",
                "doc_id": document["doc_id"],
                "error": data_response.get("error", "data node rejected document"),
            }

        with self.doc_lock:
            self.doc_count += 1

        self.log(
            f"Verified '{title or document['doc_id']}' -> block "
            f"{data_response.get('block_index')} on {data_response.get('data_node')}"
        )
        return {
            "ok": True,
            "type": "DOC_ACK",
            "doc_id": document["doc_id"],
            "content_hash": document["content_hash"],
            "data_node": data_response.get("data_node"),
            "block_index": data_response.get("block_index"),
            "block_hash": data_response.get("block_hash"),
            "message": "Document verified by Doc Node and stored by Data Node",
        }

    def build_document_record(self, payload, address):
        received_at = now_utc()
        content = str(payload.get("content", "")).strip()
        title = str(payload.get("title", "")).strip() or "Untitled"
        sender = payload.get("sender") or "anonymous-user"
        content_hash = sha256_text(content)
        doc_seed = canonical_json(
            {
                "sender": sender,
                "title": title,
                "content_hash": content_hash,
                "received_at": received_at,
                "doc_node": self.node_id,
            }
        )

        return {
            "doc_id": sha256_text(doc_seed)[:24],
            "title": title,
            "sender": sender,
            "source_user_node": packet_source(payload, address),
            "doc_node": self.node_id,
            "received_at": received_at,
            "content": content,
            "content_hash": content_hash,
            "status": "verified_by_doc_node",
        }

    def save_document(self, document):
        path = os.path.join(self.folder, f"{document['doc_id']}.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(document, file, indent=2, sort_keys=True)
            file.write("\n")

    def forward_to_data(self, document):
        if not self.data_nodes:
            return {"ok": False, "error": "no data nodes configured"}

        last_error = None
        for host, port in self.data_nodes:
            try:
                response = request(
                    host,
                    port,
                    {
                        "type": "DOC_SUBMIT",
                        "from": self.node_id,
                        "document": document,
                    },
                    timeout=10.0,
                )
                if response and response.get("ok"):
                    response["data_node"] = f"{host}:{port}"
                    return response
                last_error = response.get("error", "rejected") if response else "no response"
            except Exception as exc:
                last_error = str(exc)
                self.log(f"Data node {host}:{port} unavailable: {exc}")

        return {"ok": False, "error": last_error or "all data nodes failed"}

    def data_node_text(self):
        if not self.data_nodes:
            return "none"
        return ", ".join(f"{host}:{port}" for host, port in self.data_nodes)

    def print_status(self):
        with self.doc_lock:
            count = self.doc_count
        print()
        print(f"Node       : {self.node_id}")
        print(f"Docs saved : {count}")
        print(f"Folder     : {self.folder}")
        print(f"Data nodes : {self.data_node_text()}")


def packet_source(payload, address):
    host, port = address
    return payload.get("user_node") or f"user:{host}:{port}"


def Start_Doc():
    print()
    print("FerroFy Doc Node")
    print("This node receives User data, verifies it, and forwards it to Data nodes.")
    print()

    port = ask_int("Doc node port", DEFAULT_DOC_PORT)
    default_data = f"127.0.0.1:{DEFAULT_DATA_PORT}"
    data_raw = input(f"Data node addresses [{default_data}] > ").strip() or default_data
    data_nodes = parse_peer_list(data_raw, DEFAULT_DATA_PORT)
    folder = input(f"Document folder [{DEFAULT_DOC_FOLDER}] > ").strip() or DEFAULT_DOC_FOLDER

    node = DocNode(port=port, data_nodes=data_nodes, folder=folder)
    node.start()

    print()
    print("Commands: status, quit")
    try:
        while True:
            command = input("doc> ").strip().lower()
            if command in {"q", "quit", "exit"}:
                break
            if command in {"", "status"}:
                node.print_status()
            else:
                print("Unknown command. Use: status, quit")
    except KeyboardInterrupt:
        print()
    finally:
        node.stop()
        print("Doc node stopped.")


if __name__ == "__main__":
    Start_Doc()
