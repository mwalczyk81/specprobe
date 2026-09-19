"""Multi-mode semantic and lexical search engine using embedded Qdrant."""

from enum import StrEnum
from pathlib import Path
from typing import Any

from qdrant_client import models

from specprobe.index.embedder import FastEmbedEngine
from specprobe.index.store import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    QdrantIndexStore,
)
from specprobe.models import SearchMatch


class SearchMode(StrEnum):
    """Supported retrieval algorithms for operation search."""

    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid-rerank"


def build_filter(
    tag: str | None = None,
    method: str | None = None,
    deprecated: bool | None = None,
    source_title: str | None = None,
    source_version: str | None = None,
) -> models.Filter | None:
    """Construct Qdrant Filter from optional search CLI criteria."""
    must_conditions: list[models.Condition] = []

    if tag:
        must_conditions.append(
            models.FieldCondition(
                key="tags",
                match=models.MatchValue(value=tag),
            )
        )

    if method:
        must_conditions.append(
            models.FieldCondition(
                key="method",
                match=models.MatchValue(value=method.upper()),
            )
        )

    if deprecated is not None:
        must_conditions.append(
            models.FieldCondition(
                key="deprecated",
                match=models.MatchValue(value=deprecated),
            )
        )

    if source_title:
        must_conditions.append(
            models.FieldCondition(
                key="source_title",
                match=models.MatchValue(value=source_title),
            )
        )

    if source_version:
        must_conditions.append(
            models.FieldCondition(
                key="source_version",
                match=models.MatchValue(value=source_version),
            )
        )

    if not must_conditions:
        return None

    return models.Filter(must=must_conditions)


class SearchEngine:
    """Executes multi-mode semantic searches against local embedded Qdrant store."""

    def __init__(
        self,
        index_path: Path | str,
        embedder: FastEmbedEngine | None = None,
        collection_name: str = COLLECTION_NAME,
        store: QdrantIndexStore | None = None,
    ) -> None:
        self.index_path = Path(index_path) if str(index_path) != ":memory:" else ":memory:"
        self.collection_name = collection_name
        self.embedder = embedder if embedder is not None else FastEmbedEngine()
        self.store = store

    def search(
        self,
        query: str,
        mode: SearchMode | str = SearchMode.HYBRID,
        limit: int = 5,
        tag: str | None = None,
        method: str | None = None,
        deprecated: bool | None = None,
        source_title: str | None = None,
        source_version: str | None = None,
        full: bool = False,
    ) -> list[SearchMatch]:
        """Search operations matching query intent and metadata filters.

        Parameters
        ----------
        query : str
            Natural-language search query.
        mode : SearchMode | str
            Retrieval mode ('dense', 'hybrid', or 'hybrid-rerank').
        limit : int
            Maximum number of top matches to return.
        tag : str | None
            Filter by operation tag.
        method : str | None
            Filter by HTTP method (case-insensitive).
        deprecated : bool | None
            Filter by deprecation status.
        source_title : str | None
            Filter by source API specification title.
        source_version : str | None
            Filter by source API specification version.
        full : bool
            If True, embed complete OperationChunk payload in match.

        Returns
        -------
        list[SearchMatch]
            Ranked list of matching operations. Note that each match's score is an ordinal
            ranking metric valid only within this specific query invocation; scores are not
            calibrated probabilities and cannot be compared across different retrieval modes
            or separate queries.
        """
        if isinstance(mode, str):
            mode = SearchMode(mode.lower())

        q_filter = build_filter(
            tag=tag,
            method=method,
            deprecated=deprecated,
            source_title=source_title,
            source_version=source_version,
        )

        def _execute(client: Any) -> list[SearchMatch]:
            # Return empty results if collection is empty
            info = client.get_collection(self.collection_name)
            if not info.points_count:
                return []

            dense_vector = self.embedder.embed_query(query)

            if mode == SearchMode.DENSE:
                result = client.query_points(
                    collection_name=self.collection_name,
                    query=dense_vector,
                    using=DENSE_VECTOR_NAME,
                    query_filter=q_filter,
                    limit=limit,
                    with_payload=True,
                )
                scored_points = [(pt, float(pt.score)) for pt in result.points]

            elif mode == SearchMode.HYBRID:
                sparse_indices, sparse_values = self.embedder.embed_sparse([query])[0]
                sparse_vector = models.SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                )
                prefetch_limit = max(20, limit * 2)

                result = client.query_points(
                    collection_name=self.collection_name,
                    prefetch=[
                        models.Prefetch(
                            query=dense_vector,
                            using=DENSE_VECTOR_NAME,
                            filter=q_filter,
                            limit=prefetch_limit,
                        ),
                        models.Prefetch(
                            query=sparse_vector,
                            using=SPARSE_VECTOR_NAME,
                            filter=q_filter,
                            limit=prefetch_limit,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=q_filter,
                    limit=limit,
                    with_payload=True,
                )
                scored_points = [(pt, float(pt.score)) for pt in result.points]

            elif mode == SearchMode.HYBRID_RERANK:
                sparse_indices, sparse_values = self.embedder.embed_sparse([query])[0]
                sparse_vector = models.SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                )
                candidate_pool_limit = max(20, limit * 4)

                candidates_res = client.query_points(
                    collection_name=self.collection_name,
                    prefetch=[
                        models.Prefetch(
                            query=dense_vector,
                            using=DENSE_VECTOR_NAME,
                            filter=q_filter,
                            limit=candidate_pool_limit,
                        ),
                        models.Prefetch(
                            query=sparse_vector,
                            using=SPARSE_VECTOR_NAME,
                            filter=q_filter,
                            limit=candidate_pool_limit,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=q_filter,
                    limit=candidate_pool_limit,
                    with_payload=True,
                )

                candidate_points = candidates_res.points
                if not candidate_points:
                    scored_points = []
                else:
                    candidate_docs: list[str] = []
                    for pt in candidate_points:
                        payload = pt.payload or {}
                        doc = (
                            payload.get("embedding_text")
                            or payload.get("summary")
                            or f"{payload.get('method')} {payload.get('path')}"
                        )
                        candidate_docs.append(doc)

                    rerank_scores = self.embedder.rerank(query, candidate_docs)
                    ranked_pairs = sorted(
                        zip(candidate_points, rerank_scores, strict=True),
                        key=lambda pair: pair[1],
                        reverse=True,
                    )
                    scored_points = [(pt, float(score)) for pt, score in ranked_pairs[:limit]]

            matches: list[SearchMatch] = []
            for pt, score in scored_points:
                payload = pt.payload or {}
                matches.append(
                    SearchMatch(
                        operationId=payload.get("operation_id", ""),
                        path=payload.get("path", ""),
                        method=payload.get("method", ""),
                        score=score,
                        tags=payload.get("tags", []),
                        summary=payload.get("summary"),
                        source_title=payload.get("source_title", ""),
                        source_version=payload.get("source_version", ""),
                        chunk=payload.get("raw_chunk") if full else None,
                    )
                )

            return matches

        if self.store is not None:
            return _execute(self.store.client)

        with QdrantIndexStore(
            index_path=self.index_path, collection_name=self.collection_name
        ) as store:
            return _execute(store.client)

    def search_unranked(
        self,
        limit: int | None = None,
        tag: str | None = None,
        method: str | None = None,
        deprecated: bool | None = None,
        source_title: str | None = None,
        source_version: str | None = None,
        full: bool = False,
    ) -> list[SearchMatch]:
        """Retrieve operations matching metadata filters without ranking or embedding.

        Parameters
        ----------
        limit : int | None
            Maximum number of matches to return. If None, retrieves all matching points
            via pagination without limit truncation.
        tag : str | None
            Filter by operation tag.
        method : str | None
            Filter by HTTP method (case-insensitive).
        deprecated : bool | None
            Filter by deprecation status.
        source_title : str | None
            Filter by source API specification title.
        source_version : str | None
            Filter by source API specification version.
        full : bool
            If True, embed complete OperationChunk payload under 'chunk'.

        Returns
        -------
        list[SearchMatch]
            List of matching operations with score=0.0.
        """
        if limit is not None and limit <= 0:
            return []

        q_filter = build_filter(
            tag=tag,
            method=method,
            deprecated=deprecated,
            source_title=source_title,
            source_version=source_version,
        )

        def _execute(client: Any) -> list[SearchMatch]:
            if not client.collection_exists(self.collection_name):
                return []
            info = client.get_collection(self.collection_name)
            if not info.points_count:
                return []

            matches: list[SearchMatch] = []
            offset = None

            while True:
                batch_limit = min(250, limit - len(matches)) if limit is not None else 250
                if batch_limit <= 0:
                    break

                records, offset = client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=q_filter,
                    limit=batch_limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not records:
                    break

                for rec in records:
                    payload = rec.payload or {}
                    matches.append(
                        SearchMatch(
                            operationId=payload.get("operation_id", ""),
                            path=payload.get("path", ""),
                            method=payload.get("method", ""),
                            score=0.0,
                            tags=payload.get("tags", []),
                            summary=payload.get("summary"),
                            source_title=payload.get("source_title", ""),
                            source_version=payload.get("source_version", ""),
                            chunk=payload.get("raw_chunk") if full else None,
                        )
                    )
                    if limit is not None and len(matches) >= limit:
                        break

                if offset is None:
                    break

            return matches

        if self.store is not None:
            return _execute(self.store.client)

        with QdrantIndexStore(
            index_path=self.index_path, collection_name=self.collection_name
        ) as store:
            return _execute(store.client)
