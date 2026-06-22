import json
import sys

file_to_recreate = sys.argv[1] if len(sys.argv) > 1 else "NONE"

with open(file_to_recreate, 'r') as f:
    data = json.load(f)
    with open(file_to_recreate + "-edited", 'w') as f:
        json.dump(data, f, indent=4)