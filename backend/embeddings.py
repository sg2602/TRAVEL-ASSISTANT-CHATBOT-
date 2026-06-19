"""
embeddings.py — Local embedding generation using fastembed
Model: sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
"""

from fastembed import TextEmbedding

# Load model once at module level (cached after first load)
_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

def get_embedding(text: str) -> list[float]:
    """Generate a 384-dim embedding vector for a text string."""
    embeddings = list(_model.embed([text]))
    return embeddings[0].tolist()