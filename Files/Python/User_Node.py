import os
import time

from Protocol import get_local_ip, now_utc, parse_host_port, request

DEFAULT_DOC_PORT = 5100


def read_content(raw):
    raw = raw.strip()
    if raw.startswith("@"):
        path = raw[1:].strip().strip('"')
        if not path:
            raise ValueError("file path cannot be empty")
        with open(path, "r", encoding="utf-8") as file:
            return file.read(), os.path.abspath(path)
    return raw, None


def send_user_data(doc_host, doc_port, sender, title, content, file_path=None):
    local_ip = get_local_ip()
    packet = {
        "type": "USER_DATA",
        "from": f"user:{local_ip}",
        "payload": {
            "sender": sender,
            "title": title,
            "content": content,
            "file_path": file_path,
            "user_node": f"user:{local_ip}",
            "sent_at": now_utc(),
        },
    }
    return request(doc_host, doc_port, packet, timeout=12.0)


def Start_User():
    print()
    print("FerroFy User Node")
    print("This node sends data to a Doc Node. The Doc Node forwards it into the blockchain.")
    print()

    default_doc = f"127.0.0.1:{DEFAULT_DOC_PORT}"
    doc_raw = input(f"Doc node address [{default_doc}] > ").strip() or default_doc
    doc_host, doc_port = parse_host_port(doc_raw, DEFAULT_DOC_PORT)
    sender = input("Sender name [User] > ").strip() or "User"

    print()
    print("Enter a title and data. Use @path to send a text file. Type quit as title to stop.")
    while True:
        title = input("title> ").strip()
        if title.lower() in {"q", "quit", "exit"}:
            break
        if not title:
            title = f"User Data {int(time.time())}"

        raw_content = input("data> ").strip()
        if raw_content.lower() in {"q", "quit", "exit"}:
            break

        try:
            content, file_path = read_content(raw_content)
            if not content.strip():
                print("Nothing to send.")
                continue

            response = send_user_data(doc_host, doc_port, sender, title, content, file_path)
            if response and response.get("ok"):
                print("Stored successfully.")
                print(f"Doc ID    : {response.get('doc_id')}")
                print(f"Block     : {response.get('block_index')}")
                print(f"Block hash: {str(response.get('block_hash'))[:32]}...")
            else:
                error = response.get("error", "no response") if response else "no response"
                print(f"Failed: {error}")
        except Exception as exc:
            print(f"Failed: {exc}")

    print("User node stopped.")


if __name__ == "__main__":
    Start_User()
