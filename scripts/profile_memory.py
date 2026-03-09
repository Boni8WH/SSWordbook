import pickle
import os
import sys
import psutil
import gc
import numpy as np

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # MB

print(f"Initial Memory: {get_memory_usage():.2f} MB")

vector_path = 'data/textbook_vectors.pkl'
if os.path.exists(vector_path):
    # 1. Load Pickle
    with open(vector_path, 'rb') as f:
        vectors = pickle.load(f)
    
    print(f"After loading Pickle: {get_memory_usage():.2f} MB")
    print(f"Vector count: {len(vectors)}")
    
    # 2. Convert to list of numpy arrays (simulating search usage)
    # The app actually keeps them as list of dicts, but let's see iteration cost
    
    # Simulate search calculation overhead
    # In app: vec = np.array(item['vector']) inside loop
    # Let's see what happens if we process them
    
    first_vec = np.array(vectors[0]['vector'])
    dim = first_vec.shape[0]
    print(f"Detected vector dimension: {dim}")
    dummy_query = np.random.rand(dim)
    
    print("Simulating search processing...")
    scores = []
    for item in vectors:
        vec = np.array(item['vector']) # Converting list to numpy array every time?
        # Note: In the original code: vec = np.array(item['vector']) was done INSIDE the loop.
        # This creates a new numpy array object for every single item!
        score = np.dot(dummy_query, vec)
        scores.append(score)
        
    print(f"During search simulation: {get_memory_usage():.2f} MB")
    
    del vectors
    del scores
    gc.collect()
    print(f"After cleanup: {get_memory_usage():.2f} MB")

else:
    print("Vector file not found.")
