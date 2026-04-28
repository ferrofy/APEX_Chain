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
| Data Node | `Files/Python/main.py` option 3, or `Files/Python/Data_Node.py` | Stores approved records as hash-linked blocks and syncs with other Data Nodes |

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
| Doc Node | `5100` |
| Data Node | `5200` |

On multiple Data Nodes, use different ports such as `5200`, `5201`, `5202`.

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
python Files/Python/main.py
```

Choose `3`.

It asks:

```text
This Data Node listen IP [0.0.0.0] >
This Data Node port [5200] >
How many Doc Nodes to connect / allow [0] >
Doc Node 1 IP[:port] >
How many Data Node peers to connect / allow [0] >
Data Node peer 1 IP[:port] >
Block folder [Blocks/DataNode_5200] >
```

Use `0.0.0.0` for listen IP if you want the node to listen on all local network
interfaces.

For a second Data Node on the same machine:

```text
This Data Node port [5200] > 5201
How many Data Node peers to connect / allow [0] > 1
Data Node peer 1 IP[:port] > 127.0.0.1:5200
Block folder [Blocks/DataNode_5201] >
```

For another machine, use that machine's WiFi IP instead of `127.0.0.1`.

## 2. Start Doc Node

Run:

```bash
pythonw Files/Python/Doc_Node.pyw
```

You can also run `python Files/Python/main.py` and choose `2`.

The Doc Node asks:

```text
Doc Node Listen IP: 0.0.0.0
Doc Node Port: 5100
User Node IP: <the User machine WiFi IP>
How Many Data Nodes: <number>
Data Node 1 IP:Port: <data node WiFi IP>:5200
```

When User data arrives, the Doc GUI shows the fields and waits for:

- `Yes / Approve`: stores an audit JSON in `Files/Documents/` and forwards to Data Nodes.
- `No / Reject`: sends rejection back to the User Node.

## 3. Start User Node

Run:

```bash
pythonw Files/Python/User_Node.pyw
```

or run `python Files/Python/main.py` and choose `1`.

The User Node asks only for:

```text
Doc Node IP
Doc Node Port
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
  "creator": "doc:192.168.1.10:5100",
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
