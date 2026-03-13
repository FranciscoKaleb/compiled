from flask import Blueprint, render_template, request, jsonify, session, redirect
from .blockchain2_db import blockchain2_db
import json
import os

blockchain2_bp = Blueprint('blockchain2', __name__)

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'app_files', 'blockchain2_files', 'accounts.json')

def load_accounts():
    with open(ACCOUNTS_FILE, 'r') as f:
        return json.load(f)

@blockchain2_bp.route('/blockchain2')
def blockchain2_home():
    return render_template('blockchain2/index.html')

@blockchain2_bp.route('/blockchain2/login')
def login_page():
    return render_template('blockchain2/login.html')

@blockchain2_bp.route('/blockchain2/authorized-node/dashboard')
def authorized_node_dashboard():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/dashboard.html')

@blockchain2_bp.route('/blockchain2/authorized-node/blockchain')
def authorized_node_blockchain():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/blockchain.html')

@blockchain2_bp.route('/blockchain2/authorized-node/mempool')
def authorized_node_mempool():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/mempool.html')

@blockchain2_bp.route('/blockchain2/authorized-node/budget')
def authorized_node_budget():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/budget.html')

@blockchain2_bp.route('/blockchain2/authorized-node/transaction')
def authorized_node_transaction():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/transaction.html')

@blockchain2_bp.route('/blockchain2/authorized-node/create-block')
def authorized_node_create_block():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/authorized_node/create-block.html')

@blockchain2_bp.route('/blockchain2/node/dashboard')
def node_dashboard():
    if 'user' not in session:
        return redirect('/blockchain2/login')
    return render_template('blockchain2/node/dashboard.html')

@blockchain2_bp.route('/blockchain2/get-user')
def get_user():
    if 'user' in session:
        return jsonify({'user': session['user']})
    return jsonify({'user': None}), 401

@blockchain2_bp.route('/blockchain2/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    accounts = load_accounts()
    for user in accounts['users']:
        if user['username'] == username and user['password'] == password:
            session['user'] = {
                'username': username,
                'role': user['role'],
                'agency': user['agency'],
                'blockchain_address': user['blockchain_address'],
                'hierarchy': user['hierarchy'],
                'permissions': user['permissions']
            }
            return jsonify({'success': True, 'user': session['user']})
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@blockchain2_bp.route('/blockchain2/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'success': True})

@blockchain2_bp.route('/blockchain2/view-blockchain')
def view_blockchain():
    blockchain = blockchain2_db.get_blockchain()
    return jsonify(blockchain)

@blockchain2_bp.route('/blockchain2/view-mempool')
def view_mempool():
    mempool = blockchain2_db.get_mempool()
    return jsonify({'transactions': mempool})

@blockchain2_bp.route('/blockchain2/create-transaction', methods=['POST'])
def create_transaction():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    if 'create_transaction' not in session['user']['permissions']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    transaction = {
        'txid': f"tx_{len(blockchain2_db.get_mempool())}",
        'sender': session['user']['blockchain_address'],
        'receiver': data.get('receiver'),
        'amount': data.get('amount'),
        'description': data.get('description'),
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'status': 'pending'
    }
    
    blockchain2_db.add_to_mempool(transaction)
    return jsonify({'success': True, 'transaction': transaction})

@blockchain2_bp.route('/blockchain2/add-budget', methods=['POST'])
def add_budget():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    if 'add_budget' not in session['user']['permissions']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    data = request.json
    transaction = {
        'txid': f"tx_budget_{len(blockchain2_db.get_mempool())}",
        'type': 'budget_allocation',
        'receiver': data.get('agency'),
        'amount': data.get('amount'),
        'description': data.get('description'),
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'status': 'pending'
    }
    
    blockchain2_db.add_to_mempool(transaction)
    return jsonify({'success': True, 'transaction': transaction})

@blockchain2_bp.route('/blockchain2/create-block', methods=['POST'])
def create_block():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    if 'approve_transaction' not in session['user']['permissions']:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    mempool = blockchain2_db.get_mempool()
    if not mempool:
        return jsonify({'success': False, 'message': 'No transactions in mempool'}), 400
    
    block = blockchain2_db.create_block(mempool[:5], session['user']['blockchain_address'])
    return jsonify({'success': True, 'block': block})
