import hashlib
import hmac
import re
import secrets

SCRYPT = {'n': 2 ** 15, 'r': 8, 'p': 1, 'dklen': 32}
# n=2**15, r=8 needs 128*n*r = 32 MiB, which is exactly OpenSSL's default ceiling.
MAXMEM = 64 * 1024 * 1024
USERNAME = re.compile(r'^[A-Za-z0-9_-]{3,32}$')
MIN_PASSWORD = 10


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, maxmem=MAXMEM, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, key = stored.split('$')
        if kind != 'scrypt':
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r),
                                   p=int(p), dklen=len(key) // 2, maxmem=MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(key))


def new_token() -> tuple[str, str]:
    token = secrets.token_hex(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_username(name: str) -> None:
    if not USERNAME.match(name or ''):
        raise ValueError('Usernames are 3 to 32 letters, digits, underscores or hyphens')


def check_password(password: str) -> None:
    if len(password or '') < MIN_PASSWORD:
        raise ValueError(f'Passwords need at least {MIN_PASSWORD} characters')
