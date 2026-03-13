#!/usr/bin/env python3
import lmdb
import json
import sys

if len(sys.argv) < 2:
    print("Usage: python view_lmdb.py <db_path>")
    print("Example: python view_lmdb.py app_files/blockchain2_files/blockchain_db")
    sys.exit(1)

db_path = sys.argv[1]

try:
    env = lmdb.open(db_path, readonly=True)
    with env.begin() as txn:
        cursor = txn.cursor()
        print(f"\n=== Contents of {db_path} ===\n")
        for key, value in cursor:
            try:
                decoded_value = json.loads(value.decode('utf-8'))
                print(f"Key: {key.decode('utf-8')}")
                print(f"Value: {json.dumps(decoded_value, indent=2)}")
                print("-" * 50)
            except:
                print(f"Key: {key.decode('utf-8')}")
                print(f"Value: {value}")
                print("-" * 50)
    env.close()
except Exception as e:
    print(f"Error: {e}")
