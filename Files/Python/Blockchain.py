import hashlib
import json
import os

from Protocol import now_utc

SCHEMA = "ferrofy.block.v2"
DEFAULT_DIFFICULTY = 2
ZERO_HASH = "0" * 64
GENESIS_CREATOR = "ferrofy:genesis"
GENESIS_TIMESTAMP = "2026-04-28T00:00:00Z"


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def calculate_hash(block):
    material = {key: value for key, value in block.items() if key != "hash"}
    return sha256_text(canonical_json(material))


def mine_block(index, previous_hash, data, creator, difficulty=DEFAULT_DIFFICULTY, timestamp=None):
    block = {
        "schema": SCHEMA,
        "index": int(index),
        "timestamp": timestamp or now_utc(),
        "previous_hash": previous_hash,
        "difficulty": int(difficulty),
        "nonce": 0,
        "creator": creator,
        "data": data,
    }

    prefix = "0" * int(difficulty)
    while True:
        block["hash"] = calculate_hash(block)
        if block["hash"].startswith(prefix):
            return block
        block["nonce"] += 1


def create_genesis_block(creator, difficulty=DEFAULT_DIFFICULTY):
    return mine_block(
        0,
        ZERO_HASH,
        {
            "kind": "genesis",
            "message": "FerroFy decentralized data chain started",
        },
        GENESIS_CREATOR,
        difficulty,
        GENESIS_TIMESTAMP,
    )


def create_next_block(previous_block, data, creator, difficulty=DEFAULT_DIFFICULTY):
    return mine_block(
        previous_block["index"] + 1,
        previous_block["hash"],
        data,
        creator,
        difficulty,
    )


def validate_block(block, previous_block=None):
    required = {
        "schema",
        "index",
        "timestamp",
        "previous_hash",
        "difficulty",
        "nonce",
        "creator",
        "data",
        "hash",
    }
    missing = sorted(required.difference(block))
    if missing:
        return False, "missing fields: " + ", ".join(missing)

    if block["schema"] != SCHEMA:
        return False, f"unsupported schema: {block['schema']}"

    try:
        index = int(block["index"])
        difficulty = int(block["difficulty"])
    except Exception:
        return False, "index and difficulty must be integers"

    if index < 0:
        return False, "index cannot be negative"
    if difficulty < 0 or difficulty > 5:
        return False, "difficulty must be between 0 and 5"

    expected_hash = calculate_hash(block)
    if block["hash"] != expected_hash:
        return False, "hash does not match block contents"
    if not block["hash"].startswith("0" * difficulty):
        return False, "proof of work does not match difficulty"

    if previous_block is None:
        if index != 0:
            return False, "first block must be genesis index 0"
        if block["previous_hash"] != ZERO_HASH:
            return False, "genesis previous_hash must be zero hash"
        return True, "valid genesis"

    if index != int(previous_block["index"]) + 1:
        return False, "index is not sequential"
    if block["previous_hash"] != previous_block["hash"]:
        return False, "previous_hash does not match previous block"

    return True, "valid"


def validate_chain(chain):
    if not chain:
        return False, "chain is empty"

    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            index = block.get("index", "?") if isinstance(block, dict) else "?"
            return False, f"block {index}: {reason}"
        previous = block

    return True, "valid"


def first_invalid_block(chain):
    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            return block.get("index", "?"), reason
        previous = block
    return None, "valid"


def block_file_name(index):
    return f"block_{int(index):06d}.json"


def load_chain(folder):
    if not os.path.isdir(folder):
        return []

    blocks = []
    for file_name in os.listdir(folder):
        if not file_name.endswith(".json"):
            continue
        path = os.path.join(folder, file_name)
        try:
            with open(path, "r", encoding="utf-8") as file:
                blocks.append(json.load(file))
        except Exception:
            continue

    blocks.sort(key=lambda block: int(block.get("index", -1)))
    return blocks


def save_block(folder, block):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, block_file_name(block["index"]))
    with open(path, "w", encoding="utf-8") as file:
        json.dump(block, file, indent=2, sort_keys=True)
        file.write("\n")
    return path


def save_chain(folder, chain):
    os.makedirs(folder, exist_ok=True)

    wanted = {block_file_name(block["index"]) for block in chain}
    for file_name in os.listdir(folder):
        if file_name.endswith(".json") and file_name not in wanted:
            os.remove(os.path.join(folder, file_name))

    for block in chain:
        save_block(folder, block)


def chain_signature(chain):
    return tuple(block.get("hash", "") for block in chain)


def chain_summary(chain):
    ok, reason = validate_chain(chain)
    tip = chain[-1]["hash"] if chain else ZERO_HASH
    return {
        "valid": ok,
        "reason": reason,
        "length": len(chain),
        "tip_hash": tip,
    }


def select_consensus_chain(chains):
    valid_chains = []
    for source, chain in chains:
        ok, _reason = validate_chain(chain)
        if ok:
            valid_chains.append((source, chain))

    if not valid_chains:
        return None, "no valid chains found"

    grouped = {}
    for source, chain in valid_chains:
        signature = chain_signature(chain)
        grouped.setdefault(signature, {"sources": [], "chain": chain})
        grouped[signature]["sources"].append(source)

    best = max(
        grouped.values(),
        key=lambda item: (len(item["sources"]), len(item["chain"]), item["chain"][-1]["hash"]),
    )
    sources = ", ".join(best["sources"])
    return [dict(block) for block in best["chain"]], f"selected from {sources}"
