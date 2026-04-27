import hashlib

def SHA256(Text):
    return hashlib.sha256(Text.encode()).hexdigest()

def SHA512(Text):
    return hashlib.sha512(Text.encode()).hexdigest()