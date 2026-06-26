#!/usr/bin/env python3
"""Test embedding API rate limiting."""

import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Config
EMBEDDING_MODEL_NAME = "skylark-embedding-vision"
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/coding/v3")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

# Test chunks
test_chunks = [
    "def hello_world():\n    print('Hello, World!')",
    "class MyClass:\n    def __init__(self):\n        self.value = 42",
    "import numpy as np\narr = np.array([1, 2, 3])",
    "const express = require('express');\nconst app = express();",
    "SELECT * FROM users WHERE id = 1;",
]

print(f"🧪 Testing Embedding API Rate Limit")
print(f"   Model: {EMBEDDING_MODEL_NAME}")
print(f"   Base URL: {EMBEDDING_BASE_URL}")
print(f"   Chunks: {len(test_chunks)}")
print(f"   Delay: 0.5s")
print()

client = OpenAI(
    api_key=EMBEDDING_API_KEY,
    base_url=EMBEDDING_BASE_URL,
)

for i, chunk in enumerate(test_chunks, 1):
    start_time = time.time()
    try:
        print(f"[{i}/{len(test_chunks)}] Embedding chunk {i}...", end=" ")
        response = client.embeddings.create(
            input=chunk,
            model=EMBEDDING_MODEL_NAME,
            dimensions=1024
        )
        elapsed = time.time() - start_time
        dim = len(response.data[0].embedding)
        print(f"✅ OK ({elapsed:.2f}s, dim={dim})")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ FAIL ({elapsed:.2f}s): {e}")
    
    time.sleep(0.5)

print()
print("✅ Test complete")
