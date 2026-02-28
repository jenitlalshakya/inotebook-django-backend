import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

KEY = base64.b64decode(settings.ENCRYPTION_KEY)  # 32 bytes base64 key

def encrypt_text(plain_text: str) -> str:
    """
    Encrypts text and returns a single base64 string containing nonce + ciphertext
    """
    aesgcm = AESGCM(KEY)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode(), None)
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode()

def decrypt_text(data: str) -> str:
    """
    Decrypts the base64 string that contains nonce + ciphertext
    """
    combined = base64.b64decode(data)
    nonce = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(KEY)
    decrypted = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted.decode()
