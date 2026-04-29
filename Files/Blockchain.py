import hashlib
import json
import os
import re
import time


SCHEMA = "ferrofy.custom.medical.block.v2"
ZERO_HASH = "0" * 64
BLOCK_WINDOW_SECONDS = 100
MAX_MESSAGES_PER_BLOCK = 150
INITIAL_WALLET_BALANCE = 1_000_000
TOKEN_PER_USER_WORD = 1

USER_COST_FIELDS = (
    "name",
    "problem",
    "symptoms",
    "disease",
    "date",
    "solution",
    "extra_notes",
)


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def sha512_text(value):
    return hashlib.sha512(str(value).encode("utf-8")).hexdigest()


def unix_now():
    return int(time.time())


def count_words(value):
    return len(re.findall(r"\b[\w']+\b", str(value or "")))


def count_user_words(fields):
    return sum(count_words(fields.get(key, "")) for key in USER_COST_FIELDS)


def token_cost_for_fields(fields):
    return count_user_words(fields) * TOKEN_PER_USER_WORD


def block_number(block):
    return int(block.get("Block No", block.get("Block_No", block.get("index", 0))))


def block_timestamp(block):
    return int(block.get("Timestamp", block.get("Timestamp_Unix", 0)))


def block_messages(block):
    messages = block.get("Message")
    if isinstance(messages, list):
        return messages
    records = block.get("Records")
    if isinstance(records, list):
        return records
    data = block.get("data")
    if isinstance(data, dict):
        document = data.get("document")
        if isinstance(document, dict):
            return [build_medical_record(document)]
    return []


def block_previous_hash(block):
    return block.get("Prev Hash", block.get("Previous_Hash", block.get("previous_hash", "")))


def block_hash(block):
    return block.get("Hash", block.get("hash", ""))


def calculate_hash(block):
    block_material = {key: value for key, value in block.items() if key not in {"Hash", "hash"}}
    return sha256_text(canonical_json(block_material))


def block_file_name(index):
    return f"Block_{int(index)}.json"


def create_block(index, previous_hash, messages, creator, unix_timestamp=None):
    timestamp = int(unix_timestamp if unix_timestamp is not None else unix_now())
    block = {
        "Schema": SCHEMA,
        "Block No": int(index),
        "Timestamp": timestamp,
        "Miner/Data Node": creator,
        "Message": list(messages),
        "Prev Hash": previous_hash,
    }
    block["Hash"] = calculate_hash(block)
    return block


def create_first_block(messages, creator, unix_timestamp=None):
    return create_block(1, ZERO_HASH, messages, creator, unix_timestamp)


def create_next_block(previous_block, messages, creator, unix_timestamp=None):
    if previous_block is None:
        return create_first_block(messages, creator, unix_timestamp)
    return create_block(
        block_number(previous_block) + 1,
        block_hash(previous_block),
        messages,
        creator,
        unix_timestamp,
    )


def block_is_open(block):
    return (
        bool(block)
        and unix_now() - block_timestamp(block) < BLOCK_WINDOW_SECONDS
        and len(block_messages(block)) < MAX_MESSAGES_PER_BLOCK
    )


def append_record_to_block(block, record):
    updated = dict(block)
    updated["Message"] = block_messages(block) + [record]
    updated.pop("Records", None)
    updated.pop("data", None)
    updated.pop("Hash", None)
    updated.pop("hash", None)
    updated["Hash"] = calculate_hash(updated)
    return updated


def derive_wallet_address(document):
    fields = document.get("fields", document)
    wallet_address = str(document.get("wallet_address", "")).strip()
    if wallet_address:
        return wallet_address
    seed = canonical_json(
        {
            "source_user_node": document.get("source_user_node", ""),
            "source_user_ip": document.get("source_user_ip", ""),
            "name": fields.get("name", ""),
        }
    )
    return sha256_text(seed)


def wallet_balance_from_chain(chain, wallet_address):
    balance = INITIAL_WALLET_BALANCE
    for block in chain:
        for message in block_messages(block):
            change = message.get("Balance Change", {})
            if change.get("From User") == wallet_address:
                balance -= int(change.get("Balance Transferred", 0))
    return balance


def build_medical_record(document, data_node_id="", balance_before=None):
    fields = document.get("fields", document)
    patient_name_raw = fields.get("name") or fields.get("patient_name") or fields.get("Patient_Name", "unknown")
    wallet_address = derive_wallet_address(document)
    cost = int(document.get("token_cost", token_cost_for_fields(fields)))
    balance_after = None if balance_before is None else int(balance_before) - cost

    return {
        "Transaction Id": document.get("doc_id", sha256_text(canonical_json(document))[:24]),
        "Patient Name": sha256_text(patient_name_raw),
        "Problem": fields.get("problem") or fields.get("Problem", ""),
        "Symptoms": fields.get("symptoms") or fields.get("Symptoms", ""),
        "Disease": fields.get("disease") or fields.get("Disease", ""),
        "Solution": fields.get("solution") or fields.get("Solution", ""),
        "Timestamp": int(document.get("approved_unix", unix_now())),
        "Extra Notes": fields.get("extra_notes") or fields.get("Extra_Notes", ""),
        "Doctor Notes": document.get("doctor_note", document.get("Doctor_Notes", "")),
        "Doc Node IP": sha512_text(document.get("doc_node_ip", document.get("doc_node", ""))),
        "Balance Change": {
            "From User": wallet_address,
            "To Data Node": sha512_text(data_node_id),
            "Balance Transferred": cost,
            "Word Count": count_user_words(fields),
            "Token Per Word": TOKEN_PER_USER_WORD,
            "Balance Before": balance_before,
            "Balance After": balance_after,
        },
    }


def normalize_block(block):
    if not isinstance(block, dict):
        return block
    if "Block No" in block and "Message" in block and "Prev Hash" in block and "Hash" in block:
        return block
    previous_hash = block_previous_hash(block) or ZERO_HASH
    creator = block.get("Miner/Data Node", block.get("Creator", block.get("creator", "")))
    timestamp = block_timestamp(block) or unix_now()
    return create_block(block_number(block), previous_hash, block_messages(block), creator, timestamp)


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
                block = normalize_block(json.load(file))
            if isinstance(block, dict):
                blocks.append(block)
        except Exception:
            continue

    blocks.sort(key=block_number)
    return blocks


def save_block(folder, block):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, block_file_name(block_number(block)))
    with open(path, "w", encoding="utf-8") as file:
        json.dump(block, file, indent=2, sort_keys=True)
        file.write("\n")
    return path


def save_chain(folder, chain):
    os.makedirs(folder, exist_ok=True)
    expected_files = {block_file_name(block_number(block)) for block in chain}
    for file_name in os.listdir(folder):
        if file_name.endswith(".json") and file_name not in expected_files:
            os.remove(os.path.join(folder, file_name))
    for block in chain:
        save_block(folder, block)


def validate_block(block, previous_block=None):
    if not isinstance(block, dict):
        return False, "Block must be an object"

    required = {"Schema", "Block No", "Timestamp", "Miner/Data Node", "Message", "Prev Hash", "Hash"}
    missing = sorted(required.difference(block))
    if missing:
        return False, "Missing fields: " + ", ".join(missing)
    if block["Schema"] != SCHEMA:
        return False, f"Unsupported schema: {block['Schema']}"

    try:
        number = block_number(block)
        timestamp = block_timestamp(block)
    except Exception:
        return False, "Block No and Timestamp must be integers"
    if number < 1:
        return False, "Block No must start at 1"
    if timestamp <= 0:
        return False, "Timestamp must be a UNIX timestamp"
    if not isinstance(block.get("Message"), list):
        return False, "Message must be a list"
    if len(block["Message"]) > MAX_MESSAGES_PER_BLOCK:
        return False, f"Message can hold at most {MAX_MESSAGES_PER_BLOCK} records"
    if block_hash(block) != calculate_hash(block):
        return False, "Hash does not match block contents"

    if previous_block is None:
        if number != 1:
            return False, "First block must be Block_1"
        if block_previous_hash(block) != ZERO_HASH:
            return False, "First block Prev Hash must be zero hash"
        return True, "Valid first block"

    if number != block_number(previous_block) + 1:
        return False, "Block No is not sequential"
    if block_previous_hash(block) != block_hash(previous_block):
        return False, "Prev Hash does not match previous block"
    return True, "Valid"


def validate_chain(chain):
    if not chain:
        return True, "No blocks yet"
    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            number = block_number(block) if isinstance(block, dict) else "?"
            return False, f"Block {number}: {reason}"
        previous = block
    return True, "Valid"


def first_invalid_block(chain):
    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            return block_number(block) if isinstance(block, dict) else "?", reason
        previous = block
    return None, "Valid"


def chain_signature(chain):
    return tuple(block_hash(block) for block in chain)


def chain_message_count(chain):
    return sum(len(block_messages(block)) for block in chain)


def chain_summary(chain):
    ok, reason = validate_chain(chain)
    return {
        "valid": ok,
        "reason": reason,
        "length": len(chain),
        "messages": chain_message_count(chain),
        "tip_hash": block_hash(chain[-1]) if chain else ZERO_HASH,
    }


def select_consensus_chain(candidates):
    valid = []
    for source, chain in candidates:
        ok, _reason = validate_chain(chain)
        if ok:
            valid.append((source, chain))
    if not valid:
        return None, "No valid chains found"

    grouped = {}
    for source, chain in valid:
        signature = chain_signature(chain)
        grouped.setdefault(signature, {"sources": [], "chain": chain})
        grouped[signature]["sources"].append(source)

    best = max(
        grouped.values(),
        key=lambda item: (
            len(item["sources"]),
            chain_message_count(item["chain"]),
            len(item["chain"]),
            chain_signature(item["chain"]),
        ),
    )
    total = len(valid)
    votes = len(best["sources"])
    mode = "majority" if votes > total / 2 else "best available"
    sources = ", ".join(best["sources"])
    return [dict(block) for block in best["chain"]], f"{mode} {votes}/{total} from {sources}"
