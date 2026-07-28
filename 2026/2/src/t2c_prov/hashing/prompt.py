import hashlib
import unicodedata
import re

def hash_prompt(text: str) -> bytes:
    """
    Generate a deterministic SHA-256 hash of a prompt.
    Normalizes whitespace and case to ensure functional equivalence.
    """
    # Unicode normalization (NFKC)
    normalized = unicodedata.normalize("NFKC", text)
    # Lowercase
    normalized = normalized.lower()
    # Collapse multiple whitespaces to a single space
    normalized = re.sub(r"\s+", " ", normalized).strip()
    
    return hashlib.sha256(normalized.encode("utf-8")).digest()
