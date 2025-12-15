import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from app.services.embed_service import embed_texts

print("Starting embed…")
v = embed_texts(["Were there any pressure drops last week?"])
print("OK shape:", v.shape, "dtype:", v.dtype)
