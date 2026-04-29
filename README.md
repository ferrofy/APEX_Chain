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

- Wallet Name
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
Block folder [Blocks] >
```

For another Data Node on another machine, use that machine's WiFi IP. The port
stays `5001`.

```text
How many Data Node peers to connect [0] > 1
Data Node peer 1 IP / host [port 5001] > 192.168.1.25
Block folder [Blocks] >
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

The User Node asks for:

```text
Doc Node IP / Host
Wallet Name
```

Click `Create Wallet` or send directly to auto-create one. Each wallet starts
with `1000000` tokens. User-entered words cost `1` token each; Doctor Notes do
not cost tokens.

## Blockchain Behavior

Data Nodes keep custom medical blocks in the `Blocks` folder:

```text
Blocks/Block_1.json
Blocks/Block_2.json
Blocks/Block_3.json
```

A block stays open for `100` seconds and can hold up to `150` patient messages.
If the latest block is still open, new approved records are appended to that
block. If it is older than `100` seconds or already has `150` messages, the Data
Node mines the next block.

Each block uses this format:

```json
{
  "Block No": 1,
  "Timestamp": 1777398000,
  "Miner/Data Node": "data:192.168.1.20:5001",
  "Message": [
    {
      "Patient Name": "sha256(patient-name)",
      "Problem": "text",
      "Symptoms": "text",
      "Disease": "text",
      "Solution": "text",
      "Timestamp": 1777398000,
      "Extra Notes": "text",
      "Doctor Notes": "text",
      "Doc Node IP": "sha512(doc-node-ip)",
      "Balance Change": {
        "From User": "sha256(user-wallet)",
        "To Data Node": "sha512(data-node)",
        "Balance Transferred": 12
      }
    }
  ],
  "Prev Hash": "previous-block-hash",
  "Hash": "sha256-of-this-block"
}
```

The Doc Node signs approved documents before forwarding them, but the signature
is kept only in the audit document and is not written into the blockchain block.
The Doc Node also randomizes the connected Data Node list and gives the record
to one randomly selected reachable Data Node first.

Each Data Node checks:

- block hash matches the block contents
- block number is sequential
- `Prev Hash` matches the previous block
- wallet balance has enough tokens for the user-entered words
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
