import hashlib

def SHA256(Text):
    Hash = hashlib.sha256(Text.encode()).hexdigest()
    return Hash

def SHA512(Text):
    Hash = hashlib.sha512(Text.encode()).hexdigest()
    return Hash

print(SHA256("Vikrant"))
print(SHA512("Vikrant"))