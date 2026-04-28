# FerroFy - Local WiFi Blockchain System

FerroFy is a three-node Python system for one local WiFi network.

```text
User Node  ->  Doc Node  ->  Data Node Blockchain Network
```

## Nodes

| Node | UI | Job |
| --- | --- | --- |
| User Node | `Files/Python/User_Node.pyw` GUI | Enters data and sends it to one Doc Node |
| Doc Node | `Files/Python/Doc_Node.pyw` GUI | Reviews User data and clicks Yes / No |
| Data Node | `main.py` option 3, or `Files/Python/Data_Node.py` | Stores approved records as hash-linked blocks and syncs with other Data Nodes |

The old two-node TX/RX design was removed so the project now follows only this
three-node architecture.

## Data Fields

The User Node asks for:

- Name
- Problem
- Symptoms
- Disease
- Date
- Solution
- Extra Notes

## Default Ports

| Node | Port |
| --- | --- |
| User -> Doc Node | `5000` |
| Doc Node -> Data Node | `5001` |

Nodes do not ask for their own IP or own port. Each node listens automatically
on all local network interfaces, and setup only asks for the remote machine to
connect to.

## Running On Local WiFi

Use the WiFi IPv4 address of each machine. The apps show the detected WiFi IP
when they start. On Windows you can also run:

```bash
ipconfig
```

Look for the IPv4 address under the active WiFi adapter.

## 1. Start Data Nodes

Run from the project folder:

```bash
python main.py
```

Choose `3`.

It asks:

```text
How many Data Node peers to connect [0] >
Data Node peer 1 IP / host [port 5001] >
Block folder [Blocks/DataNode_5001] >
```

For another Data Node on another machine, use that machine's WiFi IP. The port
stays `5001`.

```text
How many Data Node peers to connect [0] > 1
Data Node peer 1 IP / host [port 5001] > 192.168.1.25
Block folder [Blocks/DataNode_5001] >
```

## 2. Start Doc Node

Run:

```bash
pythonw Files/Python/Doc_Node.pyw
```

You can also run `python main.py` and choose `2`.

The Doc Node asks:

```text
How Many Data Nodes: <number>
Data Node 1: <data node WiFi IP>
```

When User data arrives, the Doc GUI shows the fields and waits for:

- `Yes / Approve`: stores an audit JSON in `Files/Documents/` and forwards to Data Nodes.
- `No / Reject`: sends rejection back to the User Node.

## 3. Start User Node

Run:

```bash
pythonw Files/Python/User_Node.pyw
```

or run `python main.py` and choose `1`.

The User Node asks only for:

```text
Doc Node IP / Host
```

Fill the data fields and click `Send To Doc Node`. If the Doc Node is not
online yet, the User Node retries automatically every few seconds until it
connects or you click `Stop Retry`.

## Blockchain Behavior

Data Nodes do not mine and do not use nonce values. A block is simply:

```json
{
  "schema": "ferrofy.localwifi.block.v1",
  "index": 1,
  "timestamp": "2026-04-28T16:30:00Z",
  "previous_hash": "abc123...",
  "creator": "doc:192.168.1.10:5000",
  "data": {
    "kind": "approved_doc_record",
    "doc_id": "...",
    "document": {}
  },
  "hash": "sha256-of-the-block"
}
```

Each Data Node checks:

- block hash matches the block contents
- block index is sequential
- `previous_hash` matches the previous block
- peer Data Nodes have the same chain

If a Data Node finds a bad or different block, it asks connected Data Nodes for
their chains. Valid chains are grouped by block hashes, and the chain with the
most votes wins. If votes tie, the node picks the longest valid chain and uses a
deterministic hash tie-break.

Manual commands inside a Data Node:

```text
data> status
data> chain
data> peers
data> repair
data> quit
```

## Requirements

- Python 3.8+
- Standard library only: `socket`, `json`, `hashlib`, `threading`, `tkinter`

## License

MIT - see `LICENSE`.
