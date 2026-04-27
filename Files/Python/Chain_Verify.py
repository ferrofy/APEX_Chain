import hashlib
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

Folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Blocks")

def SHA256_Str(Text):
    return hashlib.sha256(Text.encode("utf-8")).hexdigest()

def SHA256_File(Path):
    with open(Path, "rb") as F:
        return hashlib.sha256(F.read()).hexdigest()

def Compute_Block_Hash(Index, Timestamp, Data, Previous_Hash):
    Raw = f"{Index}{Timestamp}{json.dumps(Data, sort_keys=True)}{Previous_Hash}"
    return SHA256_Str(Raw)

def Load_All_Blocks():
    Chain = []
    if not os.path.exists(Folder):
        return Chain
    Files = sorted(
        [F for F in os.listdir(Folder) if F.endswith(".json")],
        key=lambda F: int(F.replace(".json", ""))
    )
    for File in Files:
        Path = os.path.join(Folder, File)
        try:
            with open(Path, "r") as F:
                Block = json.load(F)
                Chain.append((Block, Path))
        except Exception as E:
            print(f"  [Corrupt] Cannot Read {File} | {E}")
    return Chain

def Verify_Block_Hash(Block):
    Recomputed = Compute_Block_Hash(
        Block["Index"],
        Block["Timestamp"],
        Block["Data"],
        Block["Previous_Hash"]
    )
    return Recomputed == Block["Hash"], Recomputed

def Verify_Full_Chain(Verbose=True):
    Entries = Load_All_Blocks()
    Corrupt = []

    if not Entries:
        if Verbose:
            print("  [Chain] No Blocks Found.")
        return [], []

    if Verbose:
        print(f"\n  [Verify] Checking {len(Entries)} Block(s) From Genesis To Tip...\n")

    for i, (Block, Path) in enumerate(Entries):
        File = os.path.basename(Path)
        File_Hash = SHA256_File(Path)

        Hash_Valid, Recomputed = Verify_Block_Hash(Block)

        if i == 0:
            Genesis_Valid = Block["Previous_Hash"] == "0" * 64
            Chain_Link_Valid = Genesis_Valid
        else:
            Prev_Block = Entries[i - 1][0]
            Chain_Link_Valid = Block["Previous_Hash"] == Prev_Block["Hash"]

        Index_Valid = Block["Index"] == i

        All_Ok = Hash_Valid and Chain_Link_Valid and Index_Valid

        if Verbose:
            Status = "OK" if All_Ok else "FAIL"
            print(f"  Block {Block['Index']:>4} | {File:<10} | File-SHA256: {File_Hash[:12]}... | Hash: {'OK' if Hash_Valid else 'FAIL'} | Link: {'OK' if Chain_Link_Valid else 'FAIL'} | [{Status}]")

        if not All_Ok:
            Corrupt.append(Block["Index"])

    if Verbose:
        if Corrupt:
            print(f"\n  [Chain] {len(Corrupt)} Corrupt Block(s) Detected At Index(es): {Corrupt}")
        else:
            print(f"\n  [Chain] All {len(Entries)} Block(s) Verified OK [PASS]")

    return [B for B, _ in Entries], Corrupt

def Get_Missing_Indices(Chain):
    if not Chain:
        return []
    Max_Index = Chain[-1]["Index"]
    Existing = {B["Index"] for B in Chain}
    return [i for i in range(0, Max_Index + 1) if i not in Existing]

def Save_Block(Block, Folder_Override=None):
    Target = Folder_Override or Folder
    os.makedirs(Target, exist_ok=True)
    Path = os.path.join(Target, f"{Block['Index']}.json")
    with open(Path, "w") as F:
        json.dump(Block, F, indent=4)
    return Path
