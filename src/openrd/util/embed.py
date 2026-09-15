from __future__ import annotations

import hashlib
import math
import struct
from typing import Iterable

import numpy as np

DIM = 256


def hashing_embed(text: str, dim: int = DIM) -> bytes:
    """Local, dependency-free character n-gram hashing embedding."""
    vec = np.zeros(dim, dtype=np.float32)
    blob = (text or "").lower()
    if not blob:
        return vec.tobytes()
    for n in (2, 3, 4):
        for i in range(max(0, len(blob) - n + 1)):
            gram = blob[i : i + n]
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            sign = 1.0 if (h & 1) else -1.0
            vec[h % dim] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tobytes()


def as_array(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()


def cosine(a: bytes | np.ndarray | None, b: bytes | np.ndarray | None) -> float:
    va = as_array(a) if isinstance(a, (bytes, bytearray)) else a
    vb = as_array(b) if isinstance(b, (bytes, bytearray)) else b
    if va is None or vb is None:
        return 0.0
    if va.shape != vb.shape:
        n = min(va.size, vb.size)
        va, vb = va[:n], vb[:n]
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def pack_f32(values: Iterable[float]) -> bytes:
    data = list(values)
    return struct.pack(f"{len(data)}f", *data)


def token_estimate(text: str) -> int:
    """Cheap token estimate (~4 chars / token)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))
