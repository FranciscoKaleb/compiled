"""Chain 3 — a cryptocurrency: UTXOs, signed spends, mining rewards.

The Bitcoin model, small enough to read in one sitting:

* There are no accounts and no balances. There are *unspent transaction
  outputs* (UTXOs) — coins sitting at addresses. Your balance is the sum of the
  UTXOs your key can unlock.
* A transaction consumes whole inputs and creates new outputs; the difference
  is the miner's fee. Every input carries a signature made with the key whose
  hash is the address holding that output.
* New coins enter only through the *coinbase* transaction a miner writes to
  itself when it finds a block: the block reward (halving every N blocks) plus
  all fees in the block.
* Difficulty adjusts toward a target block time, based on how long the last
  few blocks took.

Wallet keys are held by this server (custodial) so the demo has no client-side
crypto to install — labelled as such in the UI.

    GET  /blockchain/api/coin/state
    POST /blockchain/api/coin/wallets            {label}
    GET  /blockchain/api/coin/wallets/<address>  utxos + history
    POST /blockchain/api/coin/send               {from, to, amount, fee}
    POST /blockchain/api/coin/mine               {miner}
    GET  /blockchain/api/coin/verify
    POST /blockchain/api/coin/double-spend       {from}  try to spend one UTXO twice
    POST /blockchain/api/coin/reset
"""
import time

from flask import jsonify, request

from app.blueprints.chain import bp
from app.blueprints.chain.core import (
    address_from_public, canonical, hash_obj, meets_target, merkle_root, mine, new_keypair, now_iso,
    sha256, sign, store, verify_signature,
)

CHAIN = 'coin'
SYMBOL = 'CMP'
INITIAL_REWARD = 50.0
HALVING_INTERVAL = 10          # blocks — Bitcoin uses 210,000
TARGET_BLOCK_SECONDS = 1.0
ADJUST_EVERY = 4               # blocks — Bitcoin uses 2016
MIN_DIFF, MAX_DIFF, START_DIFF = 2, 5, 3
COINBASE_PREFIX = 'coinbase'


# ---------------------------------------------------------------------------
# Wallets (custodial, for the demo)
# ---------------------------------------------------------------------------

def wallets() -> dict:
    return store().get(CHAIN, 'wallets', {})


def create_wallet(label: str) -> dict:
    priv, pub = new_keypair()
    address = address_from_public(pub)
    all_wallets = wallets()
    all_wallets[address] = {'label': label, 'public_key': pub, 'private_key': priv, 'created': now_iso()}
    store().put(CHAIN, 'wallets', all_wallets)
    return {'address': address, 'label': label, 'public_key': pub}


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def tx_body(tx: dict) -> dict:
    """What gets signed and hashed: inputs without their signatures, plus outputs.

    A coinbase also commits its block height (BIP 34): two blocks mined in the
    same second would otherwise produce identical coinbase txids, and their
    outputs would collide in the UTXO set."""
    body = {'inputs': [{'txid': i['txid'], 'index': i['index']} for i in tx['inputs']],
            'outputs': tx['outputs'], 'timestamp': tx['timestamp']}
    if 'height' in tx:
        body['height'] = tx['height']
    return body


def reward_at(height: int) -> float:
    return INITIAL_REWARD / (2 ** (height // HALVING_INTERVAL))


def utxo_set(blocks: list[dict]) -> dict:
    """{'txid:index': {address, amount, height}} — every output not yet spent."""
    unspent: dict = {}
    for block in blocks:
        for tx in block['transactions']:
            for inp in tx['inputs']:
                unspent.pop(f"{inp['txid']}:{inp['index']}", None)
            for index, out in enumerate(tx['outputs']):
                unspent[f"{tx['txid']}:{index}"] = {'address': out['address'], 'amount': out['amount'], 'height': block['height'], 'txid': tx['txid'], 'index': index}
    return unspent


def spent_in_mempool(pending: list[dict]) -> set:
    return {f"{i['txid']}:{i['index']}" for tx in pending for i in tx['inputs']}


def validate_tx(tx: dict, unspent: dict, already_spent: set, height: int) -> str | None:
    """None if valid, else the reason. Coinbase transactions have no inputs."""
    if not tx['outputs'] or any(o['amount'] <= 0 for o in tx['outputs']):
        return 'every output must be positive'
    if hash_obj({**tx_body(tx), 'sigs': [i.get('signature', '') for i in tx['inputs']]}) != tx['txid']:
        return 'txid does not match content'
    if not tx['inputs']:
        total_out = sum(o['amount'] for o in tx['outputs'])
        return None if total_out <= reward_at(height) + tx.get('fees_claimed', 0) + 1e-9 else 'coinbase claims more than the reward'
    message = canonical(tx_body(tx))
    total_in = 0.0
    for inp in tx['inputs']:
        key = f"{inp['txid']}:{inp['index']}"
        if key in already_spent:
            return f'double spend: output {key[:14]}… is already spent'
        utxo = unspent.get(key)
        if utxo is None:
            return f'input {key[:14]}… does not exist or was already spent'
        if address_from_public(inp['public_key']) != utxo['address']:
            return 'the public key does not hash to the address that owns this output'
        if not verify_signature(inp['public_key'], message, inp['signature']):
            return 'input signature is invalid'
        total_in += utxo['amount']
    total_out = sum(o['amount'] for o in tx['outputs'])
    if total_out > total_in + 1e-9:
        return f'outputs ({total_out:.4f}) exceed inputs ({total_in:.4f})'
    return None


def build_spend(from_addr: str, to_addr: str, amount: float, fee: float, unspent: dict, reserved: set) -> dict:
    """Select UTXOs, make change, sign every input. Raises ValueError with a reason."""
    wallet = wallets().get(from_addr)
    if wallet is None:
        raise ValueError('unknown sending wallet')
    mine_ = sorted([u for k, u in unspent.items() if u['address'] == from_addr and k not in reserved], key=lambda u: -u['amount'])
    needed = amount + fee
    chosen, total = [], 0.0
    for u in mine_:
        chosen.append(u); total += u['amount']
        if total >= needed - 1e-9:
            break
    if total < needed - 1e-9:
        raise ValueError(f'insufficient funds: {total:.4f} {SYMBOL} spendable, {needed:.4f} needed (amount + fee)')
    outputs = [{'address': to_addr, 'amount': round(amount, 8)}]
    change = round(total - needed, 8)
    if change > 0:
        outputs.append({'address': from_addr, 'amount': change})      # change comes back to yourself
    tx = {'inputs': [{'txid': u['txid'], 'index': u['index'], 'public_key': wallet['public_key']} for u in chosen],
          'outputs': outputs, 'timestamp': now_iso()}
    message = canonical(tx_body(tx))
    for inp in tx['inputs']:
        inp['signature'] = sign(wallet['private_key'], message)
    tx['txid'] = hash_obj({**tx_body(tx), 'sigs': [i['signature'] for i in tx['inputs']]})
    tx['fee'] = round(fee, 8)
    return tx


def coinbase(miner: str, height: int, fees: float) -> dict:
    tx = {'inputs': [], 'outputs': [{'address': miner, 'amount': round(reward_at(height) + fees, 8)}], 'timestamp': now_iso(),
          'height': height, 'fees_claimed': round(fees, 8), 'note': f'{COINBASE_PREFIX} height {height}'}
    tx['txid'] = hash_obj({**tx_body(tx), 'sigs': []})
    return tx


# ---------------------------------------------------------------------------
# Blocks and difficulty
# ---------------------------------------------------------------------------

def header_of(block: dict) -> dict:
    return {k: block[k] for k in ('height', 'previous_hash', 'timestamp', 'merkle_root', 'difficulty', 'nonce')}


def genesis() -> dict:
    header = {'height': 0, 'previous_hash': '0' * 64, 'timestamp': '2026-01-01T00:00:00Z', 'merkle_root': merkle_root([]), 'difficulty': START_DIFF, 'nonce': 0}
    return {**header, 'hash': hash_obj(header), 'transactions': [], 'mined_in': 0, 'mined_at': 0.0, 'miner': None}


def ensure_chain():
    if store().last_block(CHAIN) is None:
        store().append_block(CHAIN, genesis())


def next_difficulty(blocks: list[dict]) -> tuple[int, str]:
    last = blocks[-1]
    if last['height'] == 0 or last['height'] % ADJUST_EVERY:
        return last['difficulty'], 'unchanged until the next adjustment window'
    window = [b for b in blocks[-ADJUST_EVERY:] if b.get('mined_at')]
    if len(window) < 2:
        return last['difficulty'], 'not enough data'
    elapsed = window[-1]['mined_at'] - window[0]['mined_at']
    average = elapsed / (len(window) - 1) if elapsed > 0 else 0
    if average < TARGET_BLOCK_SECONDS / 2 and last['difficulty'] < MAX_DIFF:
        return last['difficulty'] + 1, f'blocks averaged {average:.2f}s, faster than the {TARGET_BLOCK_SECONDS}s target → harder'
    if average > TARGET_BLOCK_SECONDS * 2 and last['difficulty'] > MIN_DIFF:
        return last['difficulty'] - 1, f'blocks averaged {average:.2f}s, slower than the {TARGET_BLOCK_SECONDS}s target → easier'
    return last['difficulty'], f'blocks averaged {average:.2f}s, close enough to the {TARGET_BLOCK_SECONDS}s target'


def check_block(block: dict, previous: dict | None, unspent_before: dict) -> dict:
    coinbases = [t for t in block['transactions'] if not t['inputs']]
    fees = 0.0
    spent: set = set()
    tx_problems = []
    for t in block['transactions']:
        if t['inputs']:
            problem = validate_tx(t, unspent_before, spent, block['height'])
            if problem:
                tx_problems.append(problem)
            spent.update(f"{i['txid']}:{i['index']}" for i in t['inputs'])
            fees += sum(unspent_before[f"{i['txid']}:{i['index']}"]['amount'] for i in t['inputs'] if f"{i['txid']}:{i['index']}" in unspent_before) - sum(o['amount'] for o in t['outputs'])
    checks = {
        'link': previous is None or block['previous_hash'] == previous['hash'],
        'header_hash': hash_obj(header_of(block)) == block['hash'],
        'merkle_root': merkle_root([t['txid'] for t in block['transactions']]) == block['merkle_root'],
        'proof_of_work': block['height'] == 0 or meets_target(block['hash'], block['difficulty']),
        'one_coinbase': block['height'] == 0 or len(coinbases) == 1,
        'coinbase_amount': block['height'] == 0 or (coinbases and sum(o['amount'] for o in coinbases[0]['outputs']) <= reward_at(block['height']) + fees + 1e-6),
        'inputs_valid': not tx_problems,
    }
    return {'height': block['height'], 'valid': all(checks.values()), 'checks': checks, 'problems': tx_problems}


def verify_all(blocks: list[dict]) -> dict:
    results, unspent = [], {}
    for i, b in enumerate(blocks):
        results.append(check_block(b, blocks[i - 1] if i else None, dict(unspent)))
        unspent = utxo_set(blocks[:i + 1])
    first_bad = next((r['height'] for r in results if not r['valid']), None)
    return {'valid': first_bad is None, 'first_invalid_height': first_bad, 'blocks': results}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _balances(unspent: dict) -> dict:
    out: dict = {}
    for u in unspent.values():
        out[u['address']] = round(out.get(u['address'], 0.0) + u['amount'], 8)
    return out


@bp.get('/api/coin/state', endpoint='api_coin_state')
def state():
    ensure_chain()
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    unspent = utxo_set(blocks)
    balances = _balances(unspent)
    reserved = spent_in_mempool(pending)
    ws = wallets()
    difficulty, why = next_difficulty(blocks)
    return jsonify({
        'ok': True, 'symbol': SYMBOL,
        'blocks': [{'height': b['height'], 'hash': b['hash'], 'previous_hash': b['previous_hash'], 'timestamp': b['timestamp'], 'difficulty': b['difficulty'],
                    'nonce': b['nonce'], 'tx_count': len(b['transactions']), 'miner': b.get('miner'), 'mined_in': b.get('mined_in'),
                    'reward': next((t['outputs'][0]['amount'] for t in b['transactions'] if not t['inputs']), 0)} for b in blocks],
        'mempool': pending, 'utxo_count': len(unspent), 'reserved_in_mempool': len(reserved),
        'wallets': [{'address': a, 'label': w['label'], 'public_key': w['public_key'], 'balance': balances.get(a, 0.0),
                     'pending_out': round(sum(u['amount'] for k, u in unspent.items() if u['address'] == a and k in reserved), 8)} for a, w in ws.items()],
        'supply': round(sum(balances.values()), 8), 'next_reward': reward_at(len(blocks)), 'next_difficulty': difficulty, 'difficulty_note': why,
        'halving_interval': HALVING_INTERVAL, 'target_block_seconds': TARGET_BLOCK_SECONDS, 'valid': verify_all(blocks)['valid'],
    })


@bp.post('/api/coin/wallets', endpoint='api_coin_wallet_new')
def wallet_new():
    data = request.get_json(silent=True) or {}
    label = str(data.get('label', '')).strip()[:40] or f'wallet {len(wallets()) + 1}'
    if len(wallets()) >= 12:
        return jsonify({'ok': False, 'error': 'enough wallets for a demo (12)'}), 429
    w = create_wallet(label)
    return jsonify({'ok': True, 'wallet': w, 'note': 'address = "cx" + SHA-256(public key)[:38]. The private key stays on the server (custodial demo).'})


@bp.get('/api/coin/wallets/<address>', endpoint='api_coin_wallet')
def wallet_detail(address):
    ensure_chain()
    blocks = store().blocks(CHAIN)
    unspent = [u for u in utxo_set(blocks).values() if u['address'] == address]
    history = []
    for b in blocks:
        for t in b['transactions']:
            received = sum(o['amount'] for o in t['outputs'] if o['address'] == address)
            spent = any(wallets().get(address, {}).get('public_key') == i.get('public_key') for i in t['inputs'])
            if received or spent:
                history.append({'height': b['height'], 'txid': t['txid'], 'coinbase': not t['inputs'], 'received': round(received, 8), 'spent_from': spent})
    return jsonify({'ok': True, 'address': address, 'utxos': unspent, 'balance': round(sum(u['amount'] for u in unspent), 8), 'history': history})


@bp.post('/api/coin/send', endpoint='api_coin_send')
def send():
    ensure_chain()
    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount', 0)); fee = float(data.get('fee', 0.01))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'amount and fee must be numbers'}), 400
    if amount <= 0 or fee < 0:
        return jsonify({'ok': False, 'error': 'amount must be positive and fee non-negative'}), 400
    to_addr = str(data.get('to', '')).strip()
    if not (to_addr.startswith('cx') and len(to_addr) == 40):
        return jsonify({'ok': False, 'error': 'destination is not a valid address'}), 400
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    unspent = utxo_set(blocks)
    try:
        tx = build_spend(str(data.get('from', '')), to_addr, amount, fee, unspent, spent_in_mempool(pending))
    except ValueError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 422
    problem = validate_tx(tx, unspent, spent_in_mempool(pending), len(blocks))
    if problem:
        return jsonify({'ok': False, 'error': problem}), 422
    store().add_pending(CHAIN, tx)
    return jsonify({'ok': True, 'transaction': tx, 'signed_message': canonical(tx_body(tx)),
                    'note': f"{len(tx['inputs'])} input(s) consumed, {len(tx['outputs'])} output(s) created" + (' (the second is your change)' if len(tx['outputs']) == 2 else '')})


@bp.post('/api/coin/double-spend', endpoint='api_coin_double_spend')
def double_spend():
    """Build two transactions that spend the same UTXO and submit both."""
    ensure_chain()
    data = request.get_json(silent=True) or {}
    from_addr = str(data.get('from', ''))
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    unspent = utxo_set(blocks)
    others = [a for a in wallets() if a != from_addr] or [from_addr]
    reserved = spent_in_mempool(pending)
    mine_ = [u for k, u in unspent.items() if u['address'] == from_addr and k not in reserved]
    if not mine_:
        return jsonify({'ok': False, 'error': 'that wallet has no spendable coins — mine a block to it first'}), 422
    coin = max(mine_, key=lambda u: u['amount'])
    amount = round(coin['amount'] * 0.6, 8)
    # Both transactions are built against the SAME unspent set, i.e. before either is seen.
    tx1 = build_spend(from_addr, others[0], amount, 0.0, {f"{coin['txid']}:{coin['index']}": coin}, set())
    tx2 = build_spend(from_addr, others[-1], amount, 0.0, {f"{coin['txid']}:{coin['index']}": coin}, set())
    results = []
    for label, tx in (('first', tx1), ('second', tx2)):
        problem = validate_tx(tx, unspent, spent_in_mempool(store().mempool(CHAIN)), len(blocks))
        if problem:
            results.append({'which': label, 'accepted': False, 'reason': problem, 'txid': tx['txid']})
        else:
            store().add_pending(CHAIN, tx)
            results.append({'which': label, 'accepted': True, 'txid': tx['txid']})
    return jsonify({'ok': True, 'utxo': f"{coin['txid'][:12]}…:{coin['index']}", 'results': results,
                    'note': 'Both are validly signed by the owner. Only one can be accepted, because the second references an output the mempool already treats as spent.'})


@bp.post('/api/coin/mine', endpoint='api_coin_mine')
def mine_block():
    ensure_chain()
    data = request.get_json(silent=True) or {}
    miner = str(data.get('miner', ''))
    if miner not in wallets():
        return jsonify({'ok': False, 'error': 'choose a wallet to receive the reward'}), 400
    blocks = store().blocks(CHAIN)
    pending = store().mempool(CHAIN)
    unspent = utxo_set(blocks)
    height = len(blocks)

    accepted, rejected, spent, fees = [], [], set(), 0.0
    for tx in pending[:20]:
        problem = validate_tx(tx, unspent, spent, height)
        if problem:
            rejected.append({'txid': tx['txid'], 'reason': problem}); continue
        accepted.append(tx)
        spent.update(f"{i['txid']}:{i['index']}" for i in tx['inputs'])
        fees += sum(unspent[f"{i['txid']}:{i['index']}"]['amount'] for i in tx['inputs']) - sum(o['amount'] for o in tx['outputs'])
    transactions = [coinbase(miner, height, round(fees, 8))] + accepted

    difficulty, why = next_difficulty(blocks)
    header = {'height': height, 'previous_hash': blocks[-1]['hash'], 'timestamp': now_iso(),
              'merkle_root': merkle_root([t['txid'] for t in transactions]), 'difficulty': difficulty}
    try:
        result = mine(header, difficulty)
    except TimeoutError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 504
    block = {**header, 'nonce': result['nonce'], 'hash': result['hash'], 'transactions': transactions,
             'mined_in': result['seconds'], 'mined_at': time.time(), 'miner': miner}
    store().append_block(CHAIN, block)
    store().remove_pending(CHAIN, [t['txid'] for t in accepted] + [r['txid'] for r in rejected])
    return jsonify({'ok': True, 'block': block, 'reward': transactions[0]['outputs'][0]['amount'], 'fees': round(fees, 8),
                    'subsidy': reward_at(height), 'rejected': rejected, 'attempts': result['attempts'], 'difficulty_note': why})


@bp.get('/api/coin/verify', endpoint='api_coin_verify')
def verify():
    ensure_chain()
    return jsonify({'ok': True, **verify_all(store().blocks(CHAIN))})


@bp.post('/api/coin/reset', endpoint='api_coin_reset')
def reset():
    store().wipe(CHAIN)
    ensure_chain()
    for label in ('Alice', 'Bob'):
        create_wallet(label)
    return jsonify({'ok': True})
