import hashlib
import json
import time
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOCKCHAIN_DIR = os.path.join(BASE_DIR, 'app_files', 'blockchain_files')

class Transaction:
    def __init__(self, sender, receiver, amount, tx_type="transfer", memo=""):
        self.tx_id = hashlib.sha256(f"{sender}{receiver}{amount}{time.time()}".encode()).hexdigest()[:16]
        self.sender = sender
        self.receiver = receiver
        self.amount = amount
        self.timestamp = datetime.now().isoformat()
        self.tx_type = tx_type
        self.memo = memo
    
    def to_dict(self):
        return {
            'tx_id': self.tx_id,
            'sender': self.sender,
            'receiver': self.receiver,
            'amount': self.amount,
            'timestamp': self.timestamp,
            'tx_type': self.tx_type,
            'memo': self.memo
        }
    
    def hash(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

class Block:
    def __init__(self, index, previous_hash, transactions):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = datetime.now().isoformat()
        self.transactions = transactions
        self.merkle_root = self.compute_merkle_root()
        self.nonce = 0
        self.hash = self.compute_hash()
    
    def compute_merkle_root(self):
        if not self.transactions:
            return hashlib.sha256(b"").hexdigest()
        
        hashes = [tx.hash() for tx in self.transactions]
        while len(hashes) > 1:
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])
            hashes = [hashlib.sha256((hashes[i] + hashes[i+1]).encode()).hexdigest() 
                     for i in range(0, len(hashes), 2)]
        return hashes[0]
    
    def compute_hash(self):
        block_data = f"{self.index}{self.previous_hash}{self.timestamp}{self.merkle_root}{self.nonce}"
        return hashlib.sha256(block_data.encode()).hexdigest()
    
    def mine_block(self, difficulty=2):
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.compute_hash()
    
    def to_dict(self):
        return {
            'index': self.index,
            'previous_hash': self.previous_hash,
            'timestamp': self.timestamp,
            'merkle_root': self.merkle_root,
            'nonce': self.nonce,
            'hash': self.hash,
            'transactions': [tx.to_dict() for tx in self.transactions]
        }

class Blockchain:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(BLOCKCHAIN_DIR, 'blockchain_data.json')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.mempool = []
        self.chain = []
        self.load_chain()
        if len(self.chain) == 0:
            self.create_genesis_block()
    
    def create_genesis_block(self):
        genesis = Block(0, "0", [])
        self.chain.append(genesis)
        self.save_chain()
    
    def add_transaction(self, transaction):
        self.mempool.append(transaction)
        return transaction.tx_id
    
    def get_mempool(self):
        return [tx.to_dict() for tx in self.mempool]
    
    def create_block(self, max_transactions=5):
        if len(self.mempool) == 0:
            return None
        
        transactions = self.mempool[:max_transactions]
        previous_hash = self.chain[-1].hash
        new_block = Block(len(self.chain), previous_hash, transactions)
        new_block.mine_block(difficulty=2)
        
        self.chain.append(new_block)
        self.save_chain()
        self.mempool = self.mempool[max_transactions:]
        
        return new_block
    
    def save_chain(self):
        data = [block.to_dict() for block in self.chain]
        with open(self.db_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_chain(self):
        self.chain = []
        if not os.path.exists(self.db_path):
            return
        
        try:
            with open(self.db_path, 'r') as f:
                data = json.load(f)
                for block_data in data:
                    transactions = []
                    for tx_data in block_data.get('transactions', []):
                        tx = Transaction(tx_data['sender'], tx_data['receiver'], tx_data['amount'], tx_data.get('tx_type', 'transfer'), tx_data.get('memo', ''))
                        tx.tx_id = tx_data['tx_id']
                        tx.timestamp = tx_data['timestamp']
                        transactions.append(tx)
                    
                    block = Block(block_data['index'], block_data['previous_hash'], transactions)
                    block.timestamp = block_data['timestamp']
                    block.merkle_root = block_data['merkle_root']
                    block.nonce = block_data['nonce']
                    block.hash = block_data['hash']
                    self.chain.append(block)
        except:
            pass
    
    def get_blockchain(self):
        self.load_chain()
        return [block.to_dict() for block in self.chain]
    
    def verify_chain(self):
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i-1]
            
            if current.previous_hash != previous.hash:
                return False
            
            recalculated_hash = current.compute_hash()
            if current.hash != recalculated_hash:
                return False
        
        return True
    
    def rehash_blocks(self):
        self.load_chain()
        results = []
        for i, block in enumerate(self.chain):
            recalculated_merkle = block.compute_merkle_root()
            recalculated_hash = block.compute_hash()
            merkle_valid = block.merkle_root == recalculated_merkle
            hash_valid = block.hash == recalculated_hash
            is_valid = merkle_valid and hash_valid
            results.append({
                'index': i,
                'stored_hash': block.hash,
                'recalculated_hash': recalculated_hash,
                'stored_merkle': block.merkle_root,
                'recalculated_merkle': recalculated_merkle,
                'valid': is_valid
            })
        return results

blockchain = Blockchain()
