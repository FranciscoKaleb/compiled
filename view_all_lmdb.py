#!/usr/bin/env python3
import lmdb
import json
import os

BLOCKCHAIN2_DIR = 'app_files/blockchain2_files'

databases = ['blockchain_db', 'state_db', 'mempool_db']

for db_name in databases:
    db_path = os.path.join(BLOCKCHAIN2_DIR, db_name)
    
    if not os.path.exists(db_path):
        print(f"\n{db_name}: NOT FOUND\n")
        continue
    
    try:
        env = lmdb.open(db_path, readonly=True)
        with env.begin() as txn:
            cursor = txn.cursor()
            print(f"\n{'='*60}")
            print(f"=== {db_name} ===")
            print(f"{'='*60}\n")
            
            count = 0
            for key, value in cursor:
                try:
                    decoded_value = json.loads(value.decode('utf-8'))
                    print(f"Key: {key.decode('utf-8')}")
                    print(f"Value: {json.dumps(decoded_value, indent=2)}")
                except:
                    print(f"Key: {key.decode('utf-8')}")
                    print(f"Value: {value}")
                print("-" * 60)
                count += 1
            
            if count == 0:
                print("(empty)")
        env.close()
    except Exception as e:
        print(f"Error reading {db_name}: {e}")
