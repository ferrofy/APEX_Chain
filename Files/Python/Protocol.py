import json
import socket
import time

MAX_PACKET_BYTES = 20 * 1024 * 1024


def now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def send_packet(sock, packet):
    payload = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sock.sendall(len(payload).to_bytes(4, byteorder="big") + payload)


def recv_exact(sock, length):
    chunks = []
    remaining = length
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_packet(sock):
    header = recv_exact(sock, 4)
    if header is None:
        return None

    length = int.from_bytes(header, byteorder="big")
    if length <= 0:
        raise ValueError("empty packet")
    if length > MAX_PACKET_BYTES:
        raise ValueError(f"packet too large: {length} bytes")

    payload = recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def request(host, port, packet, timeout=8.0):
    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        send_packet(sock, packet)
        return recv_packet(sock)


def parse_host_port(value, default_port):
    value = value.strip()
    if not value:
        raise ValueError("address cannot be empty")

    if ":" in value:
        host, port_text = value.rsplit(":", 1)
        host = host.strip()
        port_text = port_text.strip()
        if not host or not port_text:
            raise ValueError(f"invalid address: {value}")
        return host, int(port_text)

    return value, int(default_port)


def parse_peer_list(raw, default_port):
    peers = []
    seen = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        host, port = parse_host_port(item, default_port)
        key = (host, int(port))
        if key not in seen:
            peers.append(key)
            seen.add(key)
    return peers


def get_local_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()
