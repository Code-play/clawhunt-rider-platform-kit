"""政策知识库：pgvector 向量 + 关键词混合检索；无命中必须转人工。"""

from __future__ import annotations

import re
from typing import Any

from app.errors import bad_request
from app.services.embeddings import embed_literal

# 混合权重：向量语义 + 关键词覆盖（中文按字符覆盖率，兼容未分词场景）
HYBRID_VECTOR_WEIGHT = 0.60
HYBRID_KEYWORD_WEIGHT = 0.40

_CJK = re.compile(r"[\u4e00-\u9fa5]")
_QUERY_STOP_CHARS = set("的了吗呢啊吧呀是什么怎么多少哪哪里请问我想问可以能要会这个那个我们你们他们")


def _content_chars(text: str) -> set[str]:
    return {char for char in _CJK.findall(text) if char not in _QUERY_STOP_CHARS}


def _keyword_coverage(query: str, chunk: str) -> float:
    """查询中的实义汉字在文档里出现的比例（0~1），作为关键词命中信号。"""
    wanted = _content_chars(query)
    if not wanted:
        return 0.0
    present = wanted & set(_CJK.findall(chunk))
    return len(present) / len(wanted)



async def upsert_policy_doc(
    conn: Any,
    *,
    doc_name: str,
    doc_version: str,
    section: str,
    chunk: str,
    effective_date: str | None = None,
    disclaimer: str | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO policy_docs (doc_name, doc_version, section, chunk, effective_date, disclaimer, embedding)
        VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
        ON CONFLICT (doc_name, doc_version, section)
        DO UPDATE SET chunk = EXCLUDED.chunk, embedding = EXCLUDED.embedding,
                      effective_date = EXCLUDED.effective_date, disclaimer = EXCLUDED.disclaimer
        """,
        doc_name,
        doc_version,
        section,
        chunk,
        effective_date,
        disclaimer,
        embed_literal(chunk),
    )


async def search_policies(
    db: Any,
    query: str,
    *,
    min_score: float = 0.30,
    top_k: int = 3,
) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        raise bad_request("empty_query", "检索问题不能为空")
    rows = await db.fetch(
        """
        SELECT doc_name, doc_version, section, chunk, effective_date, disclaimer,
               1 - (embedding <=> $1::vector) AS vector_score,
               similarity(chunk, $2) AS keyword_score
        FROM policy_docs
        ORDER BY (1 - (embedding <=> $1::vector)) DESC
        LIMIT $3
        """,
        embed_literal(query),
        query,
        max(top_k * 4, 8),
    )
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        vector_score = float(row["vector_score"])
        searchable = f"{row['doc_name']}{row['section']}{row['chunk']}"
        keyword_score = max(float(row["keyword_score"]), _keyword_coverage(query, searchable))
        score = HYBRID_VECTOR_WEIGHT * vector_score + HYBRID_KEYWORD_WEIGHT * keyword_score
        item = {
            "doc_id": f"{row['doc_name']}-{row['doc_version']}",
            "doc_name": row["doc_name"],
            "title": f"《{row['doc_name']}》",
            "doc_version": row["doc_version"],
            "version": row["doc_version"],
            "section": row["section"],
            "effective_date": row["effective_date"],
            "disclaimer": row["disclaimer"],
            "excerpt": row["chunk"][:120],
            "chunk": row["chunk"],
            "score": round(score, 4),
            "vector_score": round(vector_score, 4),
            "keyword_score": round(keyword_score, 4),
        }
        ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    items = [item for score, item in ranked if score >= min_score][:top_k]
    handoff_required = not items
    return {
        "query": query,
        "items": items,
        "handoff_required": handoff_required,
        "message": (
            "未检索到可引用的政策条款，已转人工处理（不会编造答案）。"
            if handoff_required
            else None
        ),
    }


def format_citation(item: dict[str, Any]) -> str:
    return f"《{item['doc_name']}》{item['doc_version']}（{item['section']}）：{item['excerpt']}"


def build_policy_card(item: dict[str, Any]) -> dict[str, Any]:
    """H5 政策卡扩展：标题/版本/生效日期/正文摘要/免责声明 + 出处文案。"""
    disclaimer = item.get("disclaimer") or "以上为政策摘要，具体条款以正式文件为准。"
    return {
        "doc_id": item.get("doc_id"),
        "title": item.get("title") or f"《{item['doc_name']}》",
        "version": item.get("doc_version"),
        "effective_date": item.get("effective_date"),
        "answer": item.get("chunk") or item.get("excerpt"),
        "disclaimer": disclaimer,
    }


def build_source_label(item: dict[str, Any]) -> str:
    effective = item.get("effective_date") or "-"
    return f"出处：《{item['doc_name']}》 {item['doc_version']}（生效日期 {effective}）"
