import lmdb
import json
import os
from datetime import datetime
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCKCHAIN2_DIR = os.path.join(BASE_DIR, 'app_files', 'blockchain2_files')

class Blockchain2DB:
    def __init__(self):
        os.makedirs(BLOCKCHAIN2_DIR, exist_ok=True)
        self.blockchain_env = lmdb.open(os.path.join(BLOCKCHAIN2_DIR, 'blockchain_db'), max_dbs=1)
        self.state_env = lmdb.open(os.path.join(BLOCKCHAIN2_DIR, 'state_db'), max_dbs=1)
        self.mempool_env = lmdb.open(os.path.join(BLOCKCHAIN2_DIR, 'mempool_db'), max_dbs=1)
    
    def _encode(self, data):
        return json.dumps(data).encode('utf-8')
    
    def _decode(self, data):
        return json.loads(data.decode('utf-8')) if data else None
    
    def get_blockchain(self):
        blocks = []
        with self.blockchain_env.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if key.startswith(b'block:'):
                    blocks.append(self._decode(value))
        return {'blocks': sorted(blocks, key=lambda x: x['height']), 'height': len(blocks)}
    
    def get_mempool(self):
        transactions = []
        with self.mempool_env.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                transactions.append(self._decode(value))
        return transactions
    
    def add_to_mempool(self, transaction):
        key = f"tx:{transaction['txid']}".encode('utf-8')
        with self.mempool_env.begin(write=True) as txn:
            txn.put(key, self._encode(transaction))
    
    def get_state(self):
        accounts = {}
        with self.state_env.begin() as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if key.startswith(b'account:'):
                    addr = key.decode('utf-8').replace('account:', '')
                    accounts[addr] = self._decode(value)
        return {'accounts': accounts}
    
    def update_state(self, state):
        with self.state_env.begin(write=True) as txn:
            for addr, data in state.get('accounts', {}).items():
                key = f"account:{addr}".encode('utf-8')
                txn.put(key, self._encode(data))
    
    def create_block(self, transactions, proposer):
        blockchain = self.get_blockchain()
        height = blockchain['height']
        previous_hash = blockchain['blocks'][-1]['hash'] if blockchain['blocks'] else '0'
        
        block = {
            'height': height,
            'previous_hash': previous_hash,
            'timestamp': datetime.now().isoformat(),
            'proposer': proposer,
            'transactions': transactions,
            'tx_count': len(transactions),
            'hash': self._compute_hash(height, previous_hash, transactions)
        }
        
        # Store block
        key = f"block:{height}".encode('utf-8')
        with self.blockchain_env.begin(write=True) as txn:
            txn.put(key, self._encode(block))
        
        # Update state
        self._update_state_from_transactions(transactions)
        
        # Clear mempool
        with self.mempool_env.begin(write=True) as txn:
            cursor = txn.cursor()
            for key in list(cursor.iternext(keys=True, values=False)):
                txn.delete(key)
        
        return block
    
    def _update_state_from_transactions(self, transactions):
        state = self.get_state()
        if 'accounts' not in state:
            state['accounts'] = {}
        
        for tx in transactions:
            sender = tx.get('sender')
            receiver = tx.get('receiver')
            amount = tx.get('amount', 0)
            
            if sender not in state['accounts']:
                state['accounts'][sender] = {'balance': 0, 'transactions': []}
            if receiver not in state['accounts']:
                state['accounts'][receiver] = {'balance': 0, 'transactions': []}
            
            state['accounts'][sender]['balance'] -= amount
            state['accounts'][receiver]['balance'] += amount
            state['accounts'][sender]['transactions'].append(tx['txid'])
            state['accounts'][receiver]['transactions'].append(tx['txid'])
        
        self.update_state(state)
    
    def _compute_hash(self, height, previous_hash, transactions):
        data = f"{height}{previous_hash}{len(transactions)}{datetime.now().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

blockchain2_db = Blockchain2DB()
