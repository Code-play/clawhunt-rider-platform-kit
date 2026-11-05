"""确定性文本向量（384 维），无需外部模型；用于政策知识库的向量召回。"""

from __future__ import annotations

import hashlib
import math
import re

DIMENSION = 384
_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fa5]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    lowered = text.lower()
    tokens.extend(_ASCII_WORD.findall(lowered))
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def embed(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def embed_literal(text: str) -> str:
    """pgvector 的字符串字面量形式，供 $1::vector 使用。"""
    return "[" + ",".join(f"{value:.6f}" for value in embed(text)) + "]"
