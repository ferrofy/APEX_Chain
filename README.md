# FerroFy - Three Node Blockchain Data Network

HackIndia Spark 7 | North Region | Apex

FerroFy is a terminal-based Python project that models three machines in a
small decentralized data pipeline:

```text
User Node  ->  Doc Node  ->  Data Node Network
```

- **User Node** sends data or text-file content to a Doc Node.
- **Doc Node** verifies the payload, creates a document record, stores a local
  audit copy, and forwards the record to a Data Node.
- **Data Node** mines the record into a blockchain, shares blocks with peer
  Data Nodes, detects bad local blocks, and repairs its chain from peer
  consensus.

The project uses only Python standard-library networking, JSON packets, SHA-256
hashing, and a small proof-of-work loop.

## Project Files

| File | Role |
| --- | --- |
| `main.py` | Launcher for User, Doc, and Data node modes |
| `Files/Python/User_Node.py` | Sends user data to a Doc Node |
| `Files/Python/Doc_Node.py` | Verifies user payloads and forwards documents to Data |
| `Files/Python/Data_Node.py` | Blockchain storage node with peer sync and repair |
| `Files/Python/Blockchain.py` | Shared block creation, validation, mining, and consensus helpers |
| `Files/Python/Protocol.py` | Shared TCP JSON packet protocol |
| `Blocks/DataNode_<port>/` | Block files for each Data Node |
| `Files/Documents/` | Doc Node audit records |

Legacy `TX.py` and `RX.py` files are still present, but the current launcher
uses the three-node architecture above.

## Ports

| Node | Default Port |
| --- | --- |
| Doc Node | `5100` |
| Data Node | `5200` |

User Nodes do not listen on a port. They connect to a Doc Node only when
sending data.

## Run Locally

Open three terminals from the project folder.

### 1. Start a Data Node

```bash
python main.py
```

Choose `3`.

Suggested answers:

```text
Data node port [5200] >
Peer data nodes (comma host:port, blank for none) >
Block folder [Blocks/DataNode_5200] >
```

### 2. Start a Doc Node

```bash
python main.py
```

Choose `2`.

Suggested answers:

```text
Doc node port [5100] >
Data node addresses [127.0.0.1:5200] >
Document folder [Files/Documents] >
```

### 3. Start a User Node

```bash
python main.py
```

Choose `1`.

Suggested answers:

```text
Doc node address [127.0.0.1:5100] >
Sender name [User] >
title> My First Record
data> Hello blockchain
```

The User Node sends the payload to the Doc Node. The Doc Node verifies it and
forwards it to the Data Node. The Data Node mines a block and stores it as JSON.

## Run Multiple Data Nodes

To test decentralized repair on one machine, open two Data Nodes with different
ports and folders.

Terminal A:

```text
Data node port [5200] >
Peer data nodes (comma host:port, blank for none) >
Block folder [Blocks/DataNode_5200] >
```

Terminal B:

```text
Data node port [5200] > 5201
Peer data nodes (comma host:port, blank for none) > 127.0.0.1:5200
Block folder [Blocks/DataNode_5201] >
```

Point the Doc Node at either Data Node:

```text
Data node addresses [127.0.0.1:5200] > 127.0.0.1:5200
```

When a Data Node mines a block, it proposes that block to its peers.

## Blockchain Repair

Every Data Node validates its local chain every 15 seconds. If a block hash,
previous hash, index, schema, or proof-of-work value is wrong, the Data Node
asks its peer Data Nodes for their chains.

Repair selection works like this:

1. Ask peers for their full chains.
2. Reject invalid peer chains.
3. Group valid chains by their block hashes.
4. Select the most agreed valid chain, preferring longer chains when votes tie.
5. Replace the local chain when the local chain is invalid or behind.

You can also trigger repair manually from a running Data Node:

```text
data> repair
```

## Packet Flow

```text
USER_DATA
  User Node
    -> Doc Node

DOC_SUBMIT
  Doc Node
    -> Data Node

BLOCK_PROPOSE / GET_CHAIN
  Data Node
    <-> Peer Data Nodes
```

## Block Shape

```json
{
  "schema": "ferrofy.block.v2",
  "index": 1,
  "timestamp": "2026-04-28T16:30:00Z",
  "previous_hash": "0000...",
  "difficulty": 2,
  "nonce": 42,
  "creator": "data:192.168.1.20:5200",
  "data": {
    "kind": "document_record",
    "document": {
      "doc_id": "abc123...",
      "title": "My First Record",
      "content_hash": "..."
    }
  },
  "hash": "00..."
}
```

## Requirements

- Python 3.8+
- No external packages required

## License

MIT - see `LICENSE`.
