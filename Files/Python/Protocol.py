import json
import socket
import time

MAX_PACKET_BYTES = 20 * 1024 * 1024
DEFAULT_LISTEN_HOST = "0.0.0.0"
DOC_NODE_PORT = 5000
DATA_NODE_PORT = 5000


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


def request(host, port, packet, timeout=8.0, connect_timeout=None):
    connect_timeout = timeout if connect_timeout is None else connect_timeout
    with socket.create_connection((host, int(port)), timeout=connect_timeout) as sock:
        sock.settimeout(timeout)
        send_packet(sock, packet)
        return recv_packet(sock)


def parse_port(port_text):
    try:
        port = int(str(port_text).strip())
    except Exception as exc:
        raise ValueError(f"invalid port: {port_text}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"port must be between 1 and 65535: {port}")
    return port


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
        return host, parse_port(port_text)

    return value, parse_port(default_port)


def parse_fixed_endpoint(value, fixed_port, label="endpoint"):
    host, port = parse_host_port(value, fixed_port)
    fixed_port = parse_port(fixed_port)
    if port != fixed_port:
        raise ValueError(f"{label} uses fixed port {fixed_port}. Enter the IP/host only, or use :{fixed_port}.")
    return host, fixed_port


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
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        sock.close()

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"
