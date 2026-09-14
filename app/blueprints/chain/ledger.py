"""Chain 1 — a public ledger secured by proof of work.

Anyone may submit a record; anyone may mine. Integrity comes from the chain of
hashes plus the work needed to redo them. This is the corrected version of the
original `routes/blockchain`: content-addressed transaction ids, a persistent
mempool, full verification (links, header hashes, Merkle roots, and the PoW
target), input validation, and a tamper demo that shows detection.

    GET  /blockchain/api/ledger/state            chain summary, mempool, settings
    GET  /blockchain/api/ledger/blocks/<height>  one block with per-tx Merkle proofs
    POST /blockchain/api/ledger/transactions     {sender, receiver, amount, tx_type, memo}
    POST /blockchain/api/ledger/mine             {max_tx}
    GET  /blockchain/api/ledger/verify           every check, for every block
    POST /blockchain/api/ledger/tamper           {height, txid, amount}  edit a stored block
    POST /blockchain/api/ledger/remine           {from_height}  the attacker redoes the work
    POST /blockchain/api/ledger/settings         {difficulty}
    POST /blockchain/api/ledger/reset
"""
import time

from flask import jsonify, request

from app.blueprints.chain import bp
from app.blueprints.chain.core import (
    canonical, hash_obj, meets_target, merkle_proof, merkle_root, mine, now_iso, sha256, store,
)

CHAIN = 'ledger'
TX_TYPES = ('transfer', 'record', 'contract')
DEFAULT_DIFFICULTY = 3
MAX_DIFFICULTY = 5


def settings() -> dict:
    return store().get(CHAIN, 'settings', {'difficulty': DEFAULT_DIFFICULTY})


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def make_tx(sender: str, receiver: str, amount: float, tx_type: str, memo: str) -> dict:
    body = {'sender': sender, 'receiver': receiver, 'amount': amount, 'tx_type': tx_type,
            'memo': memo, 'timestamp': now_iso()}
    # Content-addressed: the id IS the hash of the content, so two identical
    # submissions in the same second collapse and any edit changes the id.
    return {'txid': hash_obj(body), **body}


def tx_hash(tx: dict) -> str:
    return hash_obj({k: v for k, v in tx.items() if k != 'txid'})


def header_of(block: dict) -> dict:
    return {k: block[k] for k in ('height', 'previous_hash', 'timestamp', 'merkle_root', 'difficulty', 'nonce') if k in block}


def genesis() -> dict:
    header = {'height': 0, 'previous_hash': '0' * 64, 'timestamp': '2026-01-01T00:00:00Z',
              'merkle_root': merkle_root([]), 'difficulty': 0, 'nonce': 0}
    return {**header, 'hash': hash_obj(header), 'transactions': [], 'mined_in': 0.0, 'attempts': 0}


def ensure_chain():
    if store().last_block(CHAIN) is None:
        store().append_block(CHAIN, genesis())


def check_block(block: dict, previous: dict | None) -> dict:
    """Every integrity check for one block, each reported separately."""
    checks = {
        'link': previous is None or block['previous_hash'] == previous['hash'],
        'header_hash': hash_obj(header_of(block)) == block['hash'],
        'merkle_root': merkle_root([tx_hash(t) for t in block['transactions']]) == block['merkle_root'],
        'tx_ids': all(tx_hash(t) == t['txid'] for t in block['transactions']),
        'proof_of_work': block['height'] == 0 or meets_target(block['hash'], block['difficulty']),
    }
    return {'height': block['height'], 'valid': all(checks.values()), 'checks': checks}


def verify_all(blocks: list[dict]) -> dict:
    results = [check_block(b, blocks[i - 1] if i else None) for i, b in enumerate(blocks)]
    first_bad = next((r['height'] for r in results if not r['valid']), None)
    return {'valid': first_bad is None, 'first_invalid_height': first_bad, 'blocks': results}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.get('/api/ledger/state', endpoint='api_ledger_state')
def state():
    ensure_chain()
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    summary = [{'height': b['height'], 'hash': b['hash'], 'previous_hash': b['previous_hash'], 'timestamp': b['timestamp'],
                'tx_count': len(b['transactions']), 'nonce': b['nonce'], 'difficulty': b['difficulty'],
                'mined_in': b.get('mined_in'), 'attempts': b.get('attempts'), 'tampered': b.get('tampered', False)}
               for b in blocks]
    verdict = verify_all(blocks)
    return jsonify({'ok': True, 'blocks': summary, 'mempool': pending, 'settings': settings(),
                    'height': len(blocks) - 1, 'valid': verdict['valid'], 'first_invalid_height': verdict['first_invalid_height'],
                    'total_tx': sum(len(b['transactions']) for b in blocks)})


@bp.get('/api/ledger/blocks/<int:height>', endpoint='api_ledger_block')
def block(height):
    blocks = store().blocks(CHAIN)
    if height < 0 or height >= len(blocks):
        return jsonify({'ok': False, 'error': f'no block at height {height}'}), 404
    b = blocks[height]
    leaves = [tx_hash(t) for t in b['transactions']]
    proofs = {t['txid']: merkle_proof(leaves, i) for i, t in enumerate(b['transactions'])}
    return jsonify({'ok': True, 'block': b, 'header_canonical': canonical(header_of(b)), 'leaves': leaves, 'proofs': proofs,
                    'check': check_block(b, blocks[height - 1] if height else None)})


@bp.post('/api/ledger/transactions', endpoint='api_ledger_tx')
def add_tx():
    data = request.get_json(silent=True) or {}
    sender = str(data.get('sender', '')).strip()[:64]
    receiver = str(data.get('receiver', '')).strip()[:64]
    tx_type = data.get('tx_type', 'transfer')
    memo = str(data.get('memo', '')).strip()[:200]
    try:
        amount = round(float(data.get('amount', 0)), 8)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'amount must be a number'}), 400
    if not sender or not receiver:
        return jsonify({'ok': False, 'error': 'sender and receiver are required'}), 400
    if amount <= 0:
        return jsonify({'ok': False, 'error': 'amount must be positive'}), 400
    if tx_type not in TX_TYPES:
        return jsonify({'ok': False, 'error': f'tx_type must be one of {", ".join(TX_TYPES)}'}), 400
    if len(store().mempool(CHAIN)) >= 200:
        return jsonify({'ok': False, 'error': 'mempool is full — mine a block'}), 429

    tx = make_tx(sender, receiver, amount, tx_type, memo)
    if not store().add_pending(CHAIN, tx):
        return jsonify({'ok': False, 'error': 'an identical transaction is already pending (same content, same second)'}), 409
    return jsonify({'ok': True, 'transaction': tx, 'canonical': canonical({k: v for k, v in tx.items() if k != 'txid'}),
                    'note': 'txid = SHA-256 of the canonical JSON above'})


@bp.post('/api/ledger/mine', endpoint='api_ledger_mine')
def mine_block():
    ensure_chain()
    data = request.get_json(silent=True) or {}
    max_tx = max(1, min(50, int(data.get('max_tx', 5))))
    pending = store().mempool(CHAIN)
    if not pending:
        return jsonify({'ok': False, 'error': 'the mempool is empty — add a transaction first'}), 400
    chosen = pending[:max_tx]
    previous = store().last_block(CHAIN)
    difficulty = int(settings()['difficulty'])
    header = {'height': previous['height'] + 1, 'previous_hash': previous['hash'], 'timestamp': now_iso(),
              'merkle_root': merkle_root([tx_hash(t) for t in chosen]), 'difficulty': difficulty}
    try:
        result = mine(header, difficulty)
    except TimeoutError as exc:
        return jsonify({'ok': False, 'error': f'mining took too long ({exc}); lower the difficulty'}), 504
    block = {**header, 'nonce': result['nonce'], 'hash': result['hash'], 'transactions': chosen,
             'mined_in': result['seconds'], 'attempts': result['attempts']}
    store().append_block(CHAIN, block)
    store().remove_pending(CHAIN, [t['txid'] for t in chosen])
    return jsonify({'ok': True, 'block': block, 'left_in_mempool': len(pending) - len(chosen),
                    'header_canonical': canonical(header_of(block))})


@bp.get('/api/ledger/verify', endpoint='api_ledger_verify')
def verify():
    ensure_chain()
    return jsonify({'ok': True, **verify_all(store().blocks(CHAIN))})


@bp.post('/api/ledger/tamper', endpoint='api_ledger_tamper')
def tamper():
    """Edit one transaction inside a stored block without touching anything else —
    what an attacker with database access would try."""
    data = request.get_json(silent=True) or {}
    blocks = store().blocks(CHAIN)
    try:
        height = int(data['height']); amount = float(data['amount'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'height and amount are required'}), 400
    if height <= 0 or height >= len(blocks):
        return jsonify({'ok': False, 'error': 'pick a mined block (not genesis)'}), 400
    block = blocks[height]
    if not block['transactions']:
        return jsonify({'ok': False, 'error': 'that block has no transactions'}), 400
    target = next((t for t in block['transactions'] if t['txid'] == data.get('txid')), block['transactions'][0])
    before = target['amount']
    target['amount'] = amount
    block['tampered'] = True
    store().replace_block(CHAIN, block)
    verdict = verify_all(store().blocks(CHAIN))
    return jsonify({'ok': True, 'changed': {'height': height, 'txid': target['txid'], 'from': before, 'to': amount},
                    'verify': verdict, 'note': f'The stored Merkle root and hash still describe the OLD content, so block {height} fails; '
                                               f'every later block links to a hash that is now "wrong" only in the sense that the data under it changed.'})


@bp.post('/api/ledger/remine', endpoint='api_ledger_remine')
def remine():
    """The attacker's only way out: recompute the Merkle root and re-mine the
    tampered block AND every block after it, so the chain is internally
    consistent again. The cost is the point."""
    data = request.get_json(silent=True) or {}
    blocks = store().blocks(CHAIN)
    try:
        start = int(data.get('from_height'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'from_height is required'}), 400
    if start <= 0 or start >= len(blocks):
        return jsonify({'ok': False, 'error': 'invalid height'}), 400
    started = time.perf_counter(); redone = []
    for i in range(start, len(blocks)):
        b = blocks[i]
        # Fix the tampered block's tx ids too — the attacker rewrites history consistently.
        for t in b['transactions']:
            t['txid'] = tx_hash(t)
        header = {'height': b['height'], 'previous_hash': blocks[i - 1]['hash'], 'timestamp': b['timestamp'],
                  'merkle_root': merkle_root([tx_hash(t) for t in b['transactions']]), 'difficulty': b['difficulty']}
        try:
            result = mine(header, b['difficulty'])
        except TimeoutError:
            return jsonify({'ok': False, 'error': f'gave up re-mining at height {i}'}), 504
        b.update(header, nonce=result['nonce'], hash=result['hash'], mined_in=result['seconds'], attempts=result['attempts'], tampered=True)
        store().replace_block(CHAIN, b)
        redone.append({'height': i, 'attempts': result['attempts'], 'seconds': result['seconds']})
    total = round(time.perf_counter() - started, 3)
    return jsonify({'ok': True, 'redone': redone, 'seconds': total, 'verify': verify_all(store().blocks(CHAIN)),
                    'note': f'Re-mined {len(redone)} block(s) in {total}s. On a real network the honest majority kept mining meanwhile, '
                            f'so the attacker must also outpace them — which is why "51%" is the number that matters.'})


@bp.post('/api/ledger/settings', endpoint='api_ledger_settings')
def update_settings():
    data = request.get_json(silent=True) or {}
    try:
        difficulty = max(1, min(MAX_DIFFICULTY, int(data.get('difficulty', DEFAULT_DIFFICULTY))))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'difficulty must be an integer'}), 400
    store().put(CHAIN, 'settings', {'difficulty': difficulty})
    return jsonify({'ok': True, 'settings': settings(), 'expected_attempts': 16 ** difficulty})


@bp.post('/api/ledger/reset', endpoint='api_ledger_reset')
def reset():
    store().wipe(CHAIN)
    ensure_chain()
    # A little seed so the explorer is not empty.
    for s, r, a, m in (('alice', 'bob', 12.5, 'coffee'), ('bob', 'carol', 3, 'split bill'), ('carol', 'alice', 7.25, 'refund')):
        store().add_pending(CHAIN, make_tx(s, r, a, 'transfer', m))
    return jsonify({'ok': True})
