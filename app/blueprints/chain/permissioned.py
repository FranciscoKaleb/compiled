"""Chain 2 — a permissioned ledger with proof of authority.

The rebuilt `blockchain2`: a consortium of government agencies sharing one
budget ledger. Nobody mines; a small set of known *validators* take turns
signing blocks with Ed25519 keys, and every participant can verify those
signatures. Balances are never stored — they are *derived* by replaying the
chain, so the state can never drift from the history (the original stored
balances and appended to them, which is how they went negative for `None`).

Accounts
  treasury   super_admin   validator, allocates budget
  dof        budget_admin  validator, allocates budget      (Department of Finance)
  deped      agency        spends and transfers             (Department of Education)
  doh        agency        spends and transfers             (Department of Health)
  auditor    read-only

Transactions (all signed by the sender's key, all validated twice: at submit
and again when a block is proposed):
  allocation  treasury/dof → agency         creates budget (the only "mint")
  transfer    agency → agency               moves budget
  expense     agency → external payee       spends budget out of the system

    POST /blockchain/api/permissioned/login      {username, password}
    POST /blockchain/api/permissioned/logout
    GET  /blockchain/api/permissioned/me
    GET  /blockchain/api/permissioned/state      chain, mempool, balances, participants
    POST /blockchain/api/permissioned/transactions
    POST /blockchain/api/permissioned/propose    validator only: sign a block from the mempool
    GET  /blockchain/api/permissioned/verify
    GET  /blockchain/api/permissioned/history/<account>
    POST /blockchain/api/permissioned/reset
"""
from flask import jsonify, request, session

from app.blueprints.chain import bp
from app.blueprints.chain.core import (
    canonical, hash_obj, merkle_root, new_keypair, now_iso, sign, store, verify_signature,
)

CHAIN = 'permissioned'
SESSION_KEY = 'chain_user'

PARTICIPANTS = {
    'treasury': {'name': 'National Treasury', 'role': 'super_admin', 'validator': True, 'password': 'treasury123'},
    'dof': {'name': 'Department of Finance', 'role': 'budget_admin', 'validator': True, 'password': 'dof123'},
    'deped': {'name': 'Department of Education', 'role': 'agency', 'validator': False, 'password': 'deped123'},
    'doh': {'name': 'Department of Health', 'role': 'agency', 'validator': False, 'password': 'doh123'},
    'auditor': {'name': 'Commission on Audit', 'role': 'auditor', 'validator': False, 'password': 'audit123'},
}
CAN_ALLOCATE = {'super_admin', 'budget_admin'}
CAN_SPEND = {'agency'}
TX_TYPES = ('allocation', 'transfer', 'expense')


# ---------------------------------------------------------------------------
# Participants (keys are generated once and kept in the store)
# ---------------------------------------------------------------------------

def participants() -> dict:
    """{username: {name, role, validator, public_key, password_hash, private_key}}"""
    existing = store().get(CHAIN, 'participants')
    if existing:
        return existing
    from werkzeug.security import generate_password_hash
    built = {}
    for username, info in PARTICIPANTS.items():
        priv, pub = new_keypair()
        built[username] = {'name': info['name'], 'role': info['role'], 'validator': info['validator'],
                           'public_key': pub, 'private_key': priv,           # custody by the demo server
                           'password_hash': generate_password_hash(info['password'])}
    store().put(CHAIN, 'participants', built)
    return built


def public_participants() -> list[dict]:
    return [{'username': u, 'name': p['name'], 'role': p['role'], 'validator': p['validator'], 'public_key': p['public_key']}
            for u, p in participants().items()]


def current_user():
    return session.get(SESSION_KEY)


# ---------------------------------------------------------------------------
# State is derived, never stored
# ---------------------------------------------------------------------------

def replay(blocks: list[dict]) -> tuple[dict, list[str]]:
    """Walk every committed transaction and compute balances. Returns
    (balances, problems) — problems is non-empty if history ever went negative."""
    balances = {u: 0.0 for u in PARTICIPANTS}
    problems = []
    for block in blocks:
        for tx in block['transactions']:
            kind, amount = tx['tx_type'], float(tx['amount'])
            if kind == 'allocation':
                balances[tx['receiver']] = balances.get(tx['receiver'], 0.0) + amount
            elif kind == 'transfer':
                balances[tx['sender']] -= amount
                balances[tx['receiver']] = balances.get(tx['receiver'], 0.0) + amount
            elif kind == 'expense':
                balances[tx['sender']] -= amount
            if balances.get(tx.get('sender'), 0.0) < -1e-9:
                problems.append(f"block {block['height']} tx {tx['txid'][:10]} overdrew {tx['sender']}")
    return {k: round(v, 2) for k, v in balances.items()}, problems


def tx_body(tx: dict) -> dict:
    return {k: tx[k] for k in ('tx_type', 'sender', 'receiver', 'amount', 'description', 'timestamp')}


def validate_tx(tx: dict, balances: dict, pending_spend: dict, people: dict) -> str | None:
    """Return a reason the transaction is invalid, or None."""
    kind, sender, receiver = tx['tx_type'], tx['sender'], tx['receiver']
    if kind not in TX_TYPES:
        return f'unknown tx_type {kind!r}'
    if tx['amount'] <= 0:
        return 'amount must be positive'
    if sender not in people:
        return f'unknown sender {sender!r}'
    if not verify_signature(people[sender]['public_key'], canonical(tx_body(tx)), tx['signature']):
        return 'signature does not verify against the sender\'s public key'
    if hash_obj({**tx_body(tx), 'signature': tx['signature']}) != tx['txid']:
        return 'txid does not match content'
    role = people[sender]['role']
    if kind == 'allocation':
        if role not in CAN_ALLOCATE:
            return f'{sender} ({role}) may not allocate budget'
        if receiver not in people or people[receiver]['role'] != 'agency':
            return 'allocations go to an agency'
    elif kind == 'transfer':
        if role not in CAN_SPEND:
            return f'{sender} ({role}) holds no budget to transfer'
        if receiver not in people or people[receiver]['role'] != 'agency' or receiver == sender:
            return 'transfers go to a different agency'
    elif kind == 'expense':
        if role not in CAN_SPEND:
            return f'{sender} ({role}) holds no budget to spend'
        if not receiver:
            return 'an expense needs a payee'
    if kind in ('transfer', 'expense'):
        available = balances.get(sender, 0.0) - pending_spend.get(sender, 0.0)
        if tx['amount'] > available + 1e-9:
            return f'{sender} has {available:,.2f} available (balance minus pending spends); cannot spend {tx["amount"]:,.2f}'
    return None


def pending_spend_by_sender(pending: list[dict]) -> dict:
    out: dict = {}
    for tx in pending:
        if tx['tx_type'] in ('transfer', 'expense'):
            out[tx['sender']] = out.get(tx['sender'], 0.0) + float(tx['amount'])
    return out


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

def header_of(block: dict) -> dict:
    return {k: block[k] for k in ('height', 'previous_hash', 'timestamp', 'merkle_root', 'validator')}


def genesis() -> dict:
    header = {'height': 0, 'previous_hash': '0' * 64, 'timestamp': '2026-01-01T00:00:00Z', 'merkle_root': merkle_root([]), 'validator': 'genesis'}
    return {**header, 'hash': hash_obj(header), 'signature': '', 'transactions': []}


def ensure_chain():
    participants()
    if store().last_block(CHAIN) is None:
        store().append_block(CHAIN, genesis())


def check_block(block: dict, previous: dict | None, people: dict) -> dict:
    validator = people.get(block['validator'])
    checks = {
        'link': previous is None or block['previous_hash'] == previous['hash'],
        'header_hash': hash_obj(header_of(block)) == block['hash'],
        'merkle_root': merkle_root([t['txid'] for t in block['transactions']]) == block['merkle_root'],
        'validator_known': block['height'] == 0 or bool(validator and validator['validator']),
        'block_signature': block['height'] == 0 or bool(validator and verify_signature(validator['public_key'], block['hash'], block['signature'])),
        'tx_signatures': all(t['sender'] in people and verify_signature(people[t['sender']]['public_key'], canonical(tx_body(t)), t['signature'])
                             for t in block['transactions']),
    }
    return {'height': block['height'], 'valid': all(checks.values()), 'checks': checks}


def verify_all(blocks: list[dict]) -> dict:
    people = participants()
    results = [check_block(b, blocks[i - 1] if i else None, people) for i, b in enumerate(blocks)]
    _, problems = replay(blocks)
    first_bad = next((r['height'] for r in results if not r['valid']), None)
    return {'valid': first_bad is None and not problems, 'first_invalid_height': first_bad, 'blocks': results, 'balance_problems': problems}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.post('/api/permissioned/login', endpoint='api_perm_login')
def login():
    from werkzeug.security import check_password_hash
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip().lower()
    people = participants()
    person = people.get(username)
    if not person or not check_password_hash(person['password_hash'], str(data.get('password', ''))):
        return jsonify({'ok': False, 'error': 'invalid credentials'}), 401
    session[SESSION_KEY] = {'username': username, 'name': person['name'], 'role': person['role'], 'validator': person['validator']}
    return jsonify({'ok': True, 'user': session[SESSION_KEY]})


@bp.post('/api/permissioned/logout', endpoint='api_perm_logout')
def logout():
    session.pop(SESSION_KEY, None)
    return jsonify({'ok': True})


@bp.get('/api/permissioned/me', endpoint='api_perm_me')
def me():
    return jsonify({'ok': True, 'user': current_user(),
                    'demo_accounts': [{'username': u, 'password': i['password'], 'role': i['role']} for u, i in PARTICIPANTS.items()]})


@bp.get('/api/permissioned/state', endpoint='api_perm_state')
def state():
    ensure_chain()
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    balances, problems = replay(blocks)
    verdict = verify_all(blocks)
    summary = [{'height': b['height'], 'hash': b['hash'], 'previous_hash': b['previous_hash'], 'timestamp': b['timestamp'],
                'validator': b['validator'], 'signature': b['signature'][:24] + '…' if b['signature'] else '', 'tx_count': len(b['transactions']),
                'transactions': b['transactions']} for b in blocks]
    return jsonify({'ok': True, 'blocks': summary, 'mempool': pending, 'balances': balances,
                    'pending_spend': pending_spend_by_sender(pending), 'participants': public_participants(),
                    'valid': verdict['valid'], 'balance_problems': problems, 'user': current_user(),
                    'total_allocated': round(sum(float(t['amount']) for b in blocks for t in b['transactions'] if t['tx_type'] == 'allocation'), 2)})


@bp.post('/api/permissioned/transactions', endpoint='api_perm_tx')
def add_tx():
    ensure_chain()
    user = current_user()
    if not user:
        return jsonify({'ok': False, 'error': 'log in first'}), 401
    data = request.get_json(silent=True) or {}
    try:
        amount = round(float(data.get('amount', 0)), 2)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'amount must be a number'}), 400
    people = participants()
    body = {'tx_type': data.get('tx_type', 'transfer'), 'sender': user['username'], 'receiver': str(data.get('receiver', '')).strip()[:80],
            'amount': amount, 'description': str(data.get('description', '')).strip()[:200], 'timestamp': now_iso()}
    signature = sign(people[user['username']]['private_key'], canonical(body))
    tx = {**body, 'signature': signature, 'txid': hash_obj({**body, 'signature': signature})}

    balances, _ = replay(store().blocks(CHAIN))
    problem = validate_tx(tx, balances, pending_spend_by_sender(store().mempool(CHAIN)), people)
    if problem:
        return jsonify({'ok': False, 'error': problem}), 422
    if not store().add_pending(CHAIN, tx):
        return jsonify({'ok': False, 'error': 'duplicate transaction'}), 409
    return jsonify({'ok': True, 'transaction': tx, 'signed_message': canonical(body)})


@bp.post('/api/permissioned/propose', endpoint='api_perm_propose')
def propose():
    ensure_chain()
    user = current_user()
    if not user:
        return jsonify({'ok': False, 'error': 'log in first'}), 401
    people = participants()
    if not people[user['username']]['validator']:
        return jsonify({'ok': False, 'error': f"{user['name']} is not a validator — only validators may sign blocks"}), 403
    pending = store().mempool(CHAIN)
    if not pending:
        return jsonify({'ok': False, 'error': 'nothing pending'}), 400

    # Re-validate against the committed state, in order, so a transaction that
    # became invalid (someone else spent the budget) is dropped, not committed.
    blocks = store().blocks(CHAIN)
    balances, _ = replay(blocks)
    accepted, rejected, running = [], [], {}
    for tx in pending[:20]:
        problem = validate_tx(tx, balances, running, people)
        if problem:
            rejected.append({'txid': tx['txid'], 'reason': problem})
            continue
        accepted.append(tx)
        if tx['tx_type'] in ('transfer', 'expense'):
            running[tx['sender']] = running.get(tx['sender'], 0.0) + tx['amount']
    store().remove_pending(CHAIN, [t['txid'] for t in accepted] + [r['txid'] for r in rejected])
    if not accepted:
        return jsonify({'ok': False, 'error': 'every pending transaction was invalid against the current state', 'rejected': rejected}), 422

    previous = blocks[-1]
    header = {'height': previous['height'] + 1, 'previous_hash': previous['hash'], 'timestamp': now_iso(),
              'merkle_root': merkle_root([t['txid'] for t in accepted]), 'validator': user['username']}
    block_hash = hash_obj(header)
    block = {**header, 'hash': block_hash, 'signature': sign(people[user['username']]['private_key'], block_hash), 'transactions': accepted}
    store().append_block(CHAIN, block)
    return jsonify({'ok': True, 'block': block, 'rejected': rejected, 'note': 'No nonce, no mining: the block is final the moment a known validator signs it.'})


@bp.get('/api/permissioned/verify', endpoint='api_perm_verify')
def verify():
    ensure_chain()
    return jsonify({'ok': True, **verify_all(store().blocks(CHAIN))})


@bp.get('/api/permissioned/history/<account>', endpoint='api_perm_history')
def history(account):
    ensure_chain()
    rows, running = [], 0.0
    for b in store().blocks(CHAIN):
        for t in b['transactions']:
            delta = 0.0
            if t['tx_type'] == 'allocation' and t['receiver'] == account: delta = t['amount']
            elif t['tx_type'] == 'transfer' and t['receiver'] == account: delta = t['amount']
            elif t['tx_type'] in ('transfer', 'expense') and t['sender'] == account: delta = -t['amount']
            if delta:
                running += delta
                rows.append({'height': b['height'], 'txid': t['txid'], 'tx_type': t['tx_type'], 'counterparty': t['receiver'] if delta < 0 else t['sender'],
                             'description': t['description'], 'delta': round(delta, 2), 'balance_after': round(running, 2), 'timestamp': t['timestamp']})
    return jsonify({'ok': True, 'account': account, 'rows': rows, 'balance': round(running, 2)})


@bp.post('/api/permissioned/reset', endpoint='api_perm_reset')
def reset():
    store().wipe(CHAIN)
    session.pop(SESSION_KEY, None)
    ensure_chain()
    return jsonify({'ok': True})
