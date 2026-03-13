from flask import Blueprint, render_template, request, jsonify
from .blockchain import blockchain, Transaction

blockchain_bp = Blueprint('blockchain', __name__)

@blockchain_bp.route('/blockchain')
def blockchain_page():
    return render_template('blockchain/index.html')

@blockchain_bp.route('/blockchain/view-chain')
def view_chain_page():
    return render_template('blockchain/view.html')

@blockchain_bp.route('/blockchain/add-transaction', methods=['POST'])
def add_transaction():
    data = request.json
    tx = Transaction(
        sender=data.get('sender'),
        receiver=data.get('receiver'),
        amount=float(data.get('amount')),
        tx_type=data.get('tx_type', 'transfer'),
        memo=data.get('memo', '')
    )
    tx_id = blockchain.add_transaction(tx)
    return jsonify({'success': True, 'tx_id': tx_id})

@blockchain_bp.route('/blockchain/mempool')
def get_mempool():
    return jsonify(blockchain.get_mempool())

@blockchain_bp.route('/blockchain/create-block', methods=['POST'])
def create_block():
    block = blockchain.create_block(max_transactions=5)
    if block:
        return jsonify({'success': True, 'block': block.to_dict()})
    return jsonify({'success': False, 'message': 'No transactions in mempool'})

@blockchain_bp.route('/blockchain/view')
def view_blockchain():
    chain = blockchain.get_blockchain()
    return jsonify(chain)

@blockchain_bp.route('/blockchain/verify')
def verify():
    is_valid = blockchain.verify_chain()
    return jsonify({'valid': is_valid})

@blockchain_bp.route('/blockchain/rehash')
def rehash():
    results = blockchain.rehash_blocks()
    all_valid = all(r['valid'] for r in results)
    return jsonify({'valid': all_valid, 'blocks': results})
