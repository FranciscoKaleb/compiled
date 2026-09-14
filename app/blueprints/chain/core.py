"""Shared blockchain machinery: canonical hashing, Merkle roots, proof of work,
Ed25519 keys and addresses, and a SQLite-backed store.

The three chains (public ledger, permissioned ledger, cryptocurrency) differ in
who may write and how blocks are agreed; everything below is common to them.

Why hashes here are reproducible when the old code's were not: every hash is
SHA-256 over *canonical JSON* (sorted keys, no whitespace) of exactly the
fields that define the object — never `datetime.now()` at hashing time.
"""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from flask import current_app

# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def canonical(obj) -> str:
    """The one serialisation everything is hashed over."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256(data) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj) -> str:
    return sha256(canonical(obj))


def merkle_root(hashes: list[str]) -> str:
    """Pairwise hashing up to one root; an odd leaf is paired with itself.

    Changing any transaction changes its leaf, therefore every hash above it,
    therefore the root that is committed in the block header.
    """
    if not hashes:
        return sha256(b'')
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_proof(hashes: list[str], index: int) -> list[dict]:
    """The sibling hashes needed to prove leaf `index` is in the root."""
    proof, level, idx = [], list(hashes), index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = idx ^ 1
        proof.append({'hash': level[sibling], 'position': 'right' if sibling > idx else 'left'})
        level = [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_merkle_proof(leaf: str, proof: list[dict], root: str) -> bool:
    current = leaf
    for step in proof:
        current = sha256(current + step['hash']) if step['position'] == 'right' else sha256(step['hash'] + current)
    return current == root


# ---------------------------------------------------------------------------
# Proof of work
# ---------------------------------------------------------------------------

def meets_target(block_hash: str, difficulty: int) -> bool:
    return block_hash.startswith('0' * difficulty)


def mine(header: dict, difficulty: int, max_seconds: float = 30.0) -> dict:
    """Find a nonce such that hash(header) has `difficulty` leading zero hex digits.

    Returns {nonce, hash, attempts, seconds}. Raises TimeoutError past max_seconds
    so a mis-set difficulty cannot hang the server.
    """
    header = dict(header)
    started = time.perf_counter()
    nonce = 0
    while True:
        header['nonce'] = nonce
        digest = hash_obj(header)
        if meets_target(digest, difficulty):
            return {'nonce': nonce, 'hash': digest, 'attempts': nonce + 1, 'seconds': round(time.perf_counter() - started, 3)}
        nonce += 1
        if nonce % 5000 == 0 and time.perf_counter() - started > max_seconds:
            raise TimeoutError(f'gave up after {nonce} attempts')


# ---------------------------------------------------------------------------
# Keys, signatures, addresses
# ---------------------------------------------------------------------------

def new_keypair() -> tuple[str, str]:
    """(private_hex, public_hex) — Ed25519."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    priv = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()
    pub = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return priv, pub


def sign(private_hex: str, message: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex)).sign(message.encode()).hex()


def verify_signature(public_hex: str, message: str, signature_hex: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)).verify(bytes.fromhex(signature_hex), message.encode())
        return True
    except (InvalidSignature, ValueError):
        return False


def address_from_public(public_hex: str, prefix: str = 'cx') -> str:
    """An address is a hash of the public key: short, and it hides the key until
    the first spend — exactly what Bitcoin does with RIPEMD160(SHA256(pub))."""
    return prefix + sha256(bytes.fromhex(public_hex))[:38]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class ChainStore:
    """All chains in one SQLite file, namespaced by chain name.

    blocks   : the immutable log (plus a tamper flag for the demo)
    mempool  : pending transactions
    kv       : anything else (wallets, accounts, settings) as JSON
    """

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS blocks (chain TEXT, height INTEGER, hash TEXT, data TEXT, PRIMARY KEY (chain, height));
                CREATE TABLE IF NOT EXISTS mempool (chain TEXT, txid TEXT, added REAL, data TEXT, PRIMARY KEY (chain, txid));
                CREATE TABLE IF NOT EXISTS kv (chain TEXT, key TEXT, data TEXT, PRIMARY KEY (chain, key));
            ''')

    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    # -- blocks -------------------------------------------------------------
    def blocks(self, chain: str) -> list[dict]:
        with self.lock, self._conn() as conn:
            rows = conn.execute('SELECT data FROM blocks WHERE chain=? ORDER BY height', (chain,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def last_block(self, chain: str) -> dict | None:
        with self.lock, self._conn() as conn:
            row = conn.execute('SELECT data FROM blocks WHERE chain=? ORDER BY height DESC LIMIT 1', (chain,)).fetchone()
        return json.loads(row[0]) if row else None

    def append_block(self, chain: str, block: dict) -> None:
        with self.lock, self._conn() as conn:
            conn.execute('INSERT INTO blocks (chain, height, hash, data) VALUES (?, ?, ?, ?)',
                         (chain, block['height'], block['hash'], canonical(block)))

    def replace_block(self, chain: str, block: dict) -> None:
        """Used only by the tamper demo: rewrite a stored block in place."""
        with self.lock, self._conn() as conn:
            conn.execute('UPDATE blocks SET hash=?, data=? WHERE chain=? AND height=?',
                         (block['hash'], canonical(block), chain, block['height']))

    def truncate_from(self, chain: str, height: int) -> None:
        with self.lock, self._conn() as conn:
            conn.execute('DELETE FROM blocks WHERE chain=? AND height>=?', (chain, height))

    # -- mempool ------------------------------------------------------------
    def mempool(self, chain: str) -> list[dict]:
        with self.lock, self._conn() as conn:
            rows = conn.execute('SELECT data FROM mempool WHERE chain=? ORDER BY added', (chain,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_pending(self, chain: str, tx: dict) -> bool:
        with self.lock, self._conn() as conn:
            try:
                conn.execute('INSERT INTO mempool (chain, txid, added, data) VALUES (?, ?, ?, ?)',
                             (chain, tx['txid'], time.time(), canonical(tx)))
                return True
            except sqlite3.IntegrityError:
                return False                                # duplicate txid

    def remove_pending(self, chain: str, txids: list[str]) -> None:
        with self.lock, self._conn() as conn:
            conn.executemany('DELETE FROM mempool WHERE chain=? AND txid=?', [(chain, t) for t in txids])

    # -- key/value ----------------------------------------------------------
    def get(self, chain: str, key: str, default=None):
        with self.lock, self._conn() as conn:
            row = conn.execute('SELECT data FROM kv WHERE chain=? AND key=?', (chain, key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, chain: str, key: str, value) -> None:
        with self.lock, self._conn() as conn:
            conn.execute('INSERT OR REPLACE INTO kv (chain, key, data) VALUES (?, ?, ?)', (chain, key, canonical(value)))

    def keys(self, chain: str, prefix: str = '') -> list[str]:
        with self.lock, self._conn() as conn:
            rows = conn.execute('SELECT key FROM kv WHERE chain=? AND key LIKE ?', (chain, prefix + '%')).fetchall()
        return [r[0] for r in rows]

    def wipe(self, chain: str) -> None:
        with self.lock, self._conn() as conn:
            for table in ('blocks', 'mempool', 'kv'):
                conn.execute(f'DELETE FROM {table} WHERE chain=?', (chain,))


_store: ChainStore | None = None
_store_lock = threading.Lock()


def store() -> ChainStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = ChainStore(Path(current_app.config['DB_DIR']) / 'chain.db')
    return _store


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()) + 'Z'
