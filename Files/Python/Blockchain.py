import hashlib
import json
import os
import time

from Protocol import now_utc

SCHEMA = "ferrofy.localwifi.block.v1"
ZERO_HASH = "0" * 64
GENESIS_TIMESTAMP = "2026-04-28T00:00:00Z"
GENESIS_CREATOR = "ferrofy:local-wifi-genesis"
BLOCK_WINDOW_SECONDS = 100


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_patient_name(name):
    return sha256_text(str(name))


def calculate_hash(block):
    block_material = {key: value for key, value in block.items() if key != "Hash"}
    return sha256_text(canonical_json(block_material))


def unix_now():
    return int(time.time())


def create_block(index, previous_hash, records, creator, unix_timestamp=None):
    ts = unix_timestamp if unix_timestamp is not None else unix_now()
    block = {
        "Schema": SCHEMA,
        "Block_No": int(index),
        "Timestamp_Unix": ts,
        "Date": time.strftime("%Y-%m-%d", time.gmtime(ts)),
        "Creator": creator,
        "Previous_Hash": previous_hash,
        "Records": records,
    }
    block["Hash"] = calculate_hash(block)
    return block


def create_genesis_block():
    ts = int(time.mktime(time.strptime(GENESIS_TIMESTAMP, "%Y-%m-%dT%H:%M:%SZ")))
    genesis_record = {
        "Kind": "genesis",
        "Message": "FerroFy Local WiFi Blockchain Started",
        "Patient_Name": sha256_patient_name("genesis"),
        "Problem": "",
        "Symptoms": "",
        "Disease": "",
        "Extra_Notes": "",
        "Doctor_Notes": "",
    }
    return create_block(0, ZERO_HASH, [genesis_record], GENESIS_CREATOR, ts)


def build_medical_record(document):
    fields = document.get("fields", document)
    patient_name_raw = fields.get("name") or fields.get("patient_name") or fields.get("Patient_Name", "unknown")
    return {
        "Kind": "medical_record",
        "Doc_Id": document.get("doc_id", ""),
        "Patient_Name": sha256_patient_name(patient_name_raw),
        "Problem": fields.get("problem") or fields.get("Problem", ""),
        "Symptoms": fields.get("symptoms") or fields.get("Symptoms", ""),
        "Disease": fields.get("disease") or fields.get("Disease", ""),
        "Extra_Notes": fields.get("extra_notes") or fields.get("Extra_Notes", ""),
        "Doctor_Notes": fields.get("doctor_notes") or fields.get("Doctor_Notes", ""),
    }


def block_is_open(block):
    ts = block.get("Timestamp_Unix", 0)
    return (unix_now() - ts) < BLOCK_WINDOW_SECONDS


def append_record_to_block(block, record):
    updated = dict(block)
    updated["Records"] = list(block.get("Records", [])) + [record]
    updated.pop("Hash", None)
    updated["Hash"] = calculate_hash(updated)
    return updated


def create_next_block(previous_block, records, creator, unix_timestamp=None):
    return create_block(
        int(previous_block["Block_No"]) + 1,
        previous_block["Hash"],
        records,
        creator,
        unix_timestamp,
    )


def validate_block(block, previous_block=None):
    if not isinstance(block, dict):
        return False, "Block Must Be An Object"

    required = {"Schema", "Block_No", "Timestamp_Unix", "Date", "Creator", "Previous_Hash", "Records", "Hash"}
    missing = sorted(required.difference(block))
    if missing:
        return False, "Missing Fields: " + ", ".join(missing)

    if block["Schema"] != SCHEMA:
        return False, f"Unsupported Schema: {block['Schema']}"

    try:
        index = int(block["Block_No"])
    except Exception:
        return False, "Block_No Must Be An Integer"

    if index < 0:
        return False, "Block_No Cannot Be Negative"

    expected_hash = calculate_hash(block)
    if block["Hash"] != expected_hash:
        return False, "Hash Does Not Match Block Contents"

    if previous_block is None:
        if index != 0:
            return False, "First Block Must Be Genesis Index 0"
        if block["Previous_Hash"] != ZERO_HASH:
            return False, "Genesis Previous_Hash Must Be Zero Hash"
        return True, "Valid Genesis"

    if index != int(previous_block["Block_No"]) + 1:
        return False, "Index Is Not Sequential"
    if block["Previous_Hash"] != previous_block["Hash"]:
        return False, "Previous_Hash Does Not Match Previous Block"

    return True, "Valid"


def validate_chain(chain):
    if not chain:
        return False, "Chain Is Empty"

    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            index = block.get("Block_No", "?") if isinstance(block, dict) else "?"
            return False, f"Block {index}: {reason}"
        previous = block

    return True, "Valid"


def first_invalid_block(chain):
    previous = None
    for block in chain:
        ok, reason = validate_block(block, previous)
        if not ok:
            return block.get("Block_No", "?") if isinstance(block, dict) else "?", reason
        previous = block
    return None, "Valid"


def block_file_name(index):
    return f"Block_{int(index)}.json"


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

    blocks.sort(key=lambda block: int(block.get("Block_No", -1)))
    return blocks


def save_block(folder, block):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, block_file_name(block["Block_No"]))
    with open(path, "w", encoding="utf-8") as file:
        json.dump(block, file, indent=2, sort_keys=True)
        file.write("\n")
    return path


def save_chain(folder, chain):
    os.makedirs(folder, exist_ok=True)

    expected_files = {block_file_name(block["Block_No"]) for block in chain}
    for file_name in os.listdir(folder):
        if file_name.endswith(".json") and file_name not in expected_files:
            os.remove(os.path.join(folder, file_name))

    for block in chain:
        save_block(folder, block)


def chain_signature(chain):
    return tuple(block.get("Hash", "") for block in chain)


def chain_summary(chain):
    ok, reason = validate_chain(chain)
    return {
        "valid": ok,
        "reason": reason,
        "length": len(chain),
        "tip_hash": chain[-1]["Hash"] if chain else ZERO_HASH,
    }


def select_consensus_chain(candidates):
    valid = []
    for source, chain in candidates:
        ok, _reason = validate_chain(chain)
        if ok:
            valid.append((source, chain))

    if not valid:
        return None, "No Valid Chains Found"

    grouped = {}
    for source, chain in valid:
        signature = chain_signature(chain)
        grouped.setdefault(signature, {"sources": [], "chain": chain})
        grouped[signature]["sources"].append(source)

    best = max(
        grouped.values(),
        key=lambda item: (
            len(item["sources"]),
            len(item["chain"]),
            item["chain"][-1]["Hash"],
        ),
    )
    total = len(valid)
    votes = len(best["sources"])
    mode = "Majority" if votes > total / 2 else "Best Available"
    sources = ", ".join(best["sources"])
    return [dict(block) for block in best["chain"]], f"{mode} {votes}/{total} From {sources}"
