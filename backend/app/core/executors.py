# app/core/executors.py
from concurrent.futures import ThreadPoolExecutor

faiss_executor = ThreadPoolExecutor(max_workers=2)
