import hashlib


def SHA256(Text):
    return hashlib.sha256(Text.encode("utf-8")).hexdigest()


def SHA256_Bytes(Data):
    return hashlib.sha256(Data).hexdigest()


def SHA256_File(Path):
    with open(Path, "rb") as F:
        return hashlib.sha256(F.read()).hexdigest()


def SHA512(Text):
    return hashlib.sha512(Text.encode("utf-8")).hexdigest()
