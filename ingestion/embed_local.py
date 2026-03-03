# ingestion/embed_local.py
import os
from sentence_transformers import SentenceTransformer
import numpy as np

_MODEL_NAME = "intfloat/multilingual-e5-small"
_model = None


def get_model():
    global _model
    if _model is None:
        # ให้ใช้ cache ของ HF ตาม env ถ้ามี (Render แนะนำ /tmp)
        # sentence-transformers จะใช้ HF cache อัตโนมัติ
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_passages(texts: list[str]) -> list[list[float]]:
    model = get_model()
    inputs = [f"passage: {t}" for t in texts]
    vecs = model.encode(inputs, normalize_embeddings=True)
    return vecs.astype(np.float32).tolist()


def embed_query(text: str) -> list[float]:
    model = get_model()
    vec = model.encode([f"query: {text}"], normalize_embeddings=True)[0]
    return vec.astype(np.float32).tolist()