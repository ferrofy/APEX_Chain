# 🔗 FerroFy — Distributed Blockchain Node Network

> **HackIndia Spark 7 | North Region | Apex**  
> A Real Terminal-Based P2P Blockchain Built From Scratch In Python

---

## 🚀 How It Works

```
[Run main.pyw]
      │
      ├─ Verify Local Chain (Genesis → Tip, Block-By-Block SHA256)
      │
      ├─ Scan LAN For Peers On Port 5000
      │
      ├── Peers Found?  ──► RX Mode (Sync + Majority Recovery)
      │
      └── No Peers? ──────► TX Mode (Origin Node, Mine Blocks)
```

---

## 🏗 Architecture

| File | Role |
|---|---|
| `main.pyw` | Rich Terminal Launcher — Network Scan, Chain Inspect, Mode Decision |
| `Files/Python/TX.py` | Transmitter Node — Genesis, Mining, Peer Broadcast |
| `Files/Python/RX.py` | Receiver Node — Discovery, Majority Consensus, Chain Recovery |
| `Files/Python/Chain_Verify.py` | Shared Library — SHA256 Verification, Chain Validation |
| `Hash.py` | Utility — SHA256 / SHA512 / File Hash |
| `Blocks/` | Storage — One `.json` File Per Block |

---

## 🔒 Block Integrity Verification

Every Block File Is Verified **Before** Being Added Or Mined:

```
SHA256(Block_File_Contents)  ──► Compared To Block["Hash"]
Block["Previous_Hash"]       ──► Must Match SHA256 Of Previous Block Data
Block["Index"]               ──► Must Be Sequential (0, 1, 2, ...)
```

Chain Is Walked **From Genesis (Block 0) To The Tip** Every Time A New Block Is Mined Or Received.

---

## 🌐 Peer-To-Peer Network

- **Port**: `5000` (TCP)
- **Handshake**: `"Mine_RX"` ↔ `"Mine_TX"` Token Exchange
- **Discovery**: Full LAN Subnet Scan (`x.x.x.1 → x.x.x.254`)
- **Broadcast**: TX Sends Each Mined Block To All Connected Peers Instantly

---

## ⚕ Majority Consensus Recovery

When A Node Detects Missing Or Corrupt Blocks:

```
┌─────────────────────────────────────────────────────────┐
│  1. Connect To All N Available Peers                    │
│  2. Request The Full Chain From All N Nodes             │
│  3. For Each Block Index (0 → Tip):                     │
│     ─ Collect Responses From All Peers                  │
│     ─ Apply 50% + 1 Majority Vote                       │
│     ─ Winner Block Is Validated (Hash + Link)           │
│     ─ Written To Disk Only If Valid                     │
│  4. Corrupt / Missing Blocks Are Replaced               │
│  5. Node Continues Normally After Recovery              │
└─────────────────────────────────────────────────────────┘
```

> **Example:** If 5 Nodes Are Connected And 3 Agree On Block 7,  
> Block 7 From That Majority Is Accepted. (3 > 5/2 = Majority)

---

## 📦 Block Structure

```json
{
    "Index":         3,
    "Timestamp":     1777311032.703491,
    "Previous_Hash": "abc123...64-char-hex",
    "Hash":          "def456...64-char-hex",
    "Data": {
        "Message":    "Hello Blockchain",
        "Node":       "192.168.1.10",
        "Block_Time": "2026-04-27T12:00:00Z"
    }
}
```

---

## ▶ Running

```bash
python main.pyw
```

- **First Run / No Peers Detected** → TX Mode: Creates Genesis Block, Accepts Connections
- **Peers Detected On LAN** → RX Mode: Syncs Chain, Recovers If Needed, Receives New Blocks

---

## 🛠 Requirements

- Python `3.8+`
- Standard Library Only (`socket`, `hashlib`, `json`, `threading`, `os`, `time`)
- **No External Packages Required**

---

## 👥 Team

| Name | Role |
|---|---|
| **FerroFy** | Lead Architect, Blockchain Core |

---

## 📄 License

MIT — See `LICENSE`