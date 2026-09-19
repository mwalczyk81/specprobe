"""Embedded Qdrant vector store manager for SpecProbe operations."""

import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from specprobe.models import IndexStatsReport, SpecStatBreakdown

COLLECTION_NAME = "specprobe_operations"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
DENSE_VECTOR_SIZE = 384


def get_point_id(source_title: str, source_version: str, operation_id: str) -> str:
    """Generate a deterministic UUIDv5 identifier for an operation chunk point."""
    key = f"{source_title}:{source_version}:{operation_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


class QdrantIndexStore:
    """Manages the local on-disk embedded Qdrant database."""

    def __init__(self, index_path: Path | str, collection_name: str = COLLECTION_NAME) -> None:
        self.index_path = Path(index_path) if str(index_path) != ":memory:" else ":memory:"
        self.collection_name = collection_name
        if self.index_path != ":memory:":
            Path(self.index_path).mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(self.index_path))
        else:
            self.client = QdrantClient(":memory:")

        self.ensure_collection()

    def close(self) -> None:
        """Close client and release on-disk storage locks."""
        if hasattr(self, "client"):
            try:
                self.client.close()
            except Exception:
                pass

    def __enter__(self) -> "QdrantIndexStore":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def ensure_collection(self) -> None:
        """Create the collection and configure named vectors and payload indices if missing."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=DENSE_VECTOR_SIZE,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(),
                },
            )

            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                keyword_fields = [
                    "source_title",
                    "source_version",
                    "operation_id",
                    "method",
                    "tags",
                    "generation_id",
                ]
                for field in keyword_fields:
                    try:
                        self.client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name=field,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                        )
                    except Exception:
                        pass

                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="deprecated",
                        field_schema=models.PayloadSchemaType.BOOL,
                    )
                except Exception:
                    pass

    def upsert_points(self, points: list[models.PointStruct]) -> None:
        """Batch upsert vector points into the collection."""
        if not points:
            return
        self.client.upsert(collection_name=self.collection_name, points=points)

    def delete_prior_generations(
        self,
        source_title: str,
        source_version: str,
        current_generation_id: str,
    ) -> None:
        """Purge all points for (source_title, source_version) belonging to older generations."""
        filter_criteria = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_title",
                    match=models.MatchValue(value=source_title),
                ),
                models.FieldCondition(
                    key="source_version",
                    match=models.MatchValue(value=source_version),
                ),
            ],
            must_not=[
                models.FieldCondition(
                    key="generation_id",
                    match=models.MatchValue(value=current_generation_id),
                )
            ],
        )
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=filter_criteria),
        )

    def get_stats(self) -> IndexStatsReport:
        """Inspect the collection and construct a diagnostic status report."""
        if not self.client.collection_exists(self.collection_name):
            return IndexStatsReport(
                total_operations=0,
                unique_specifications=0,
                specifications=[],
                vector_dimensions={
                    "dense": f"{DENSE_VECTOR_SIZE} (Cosine)",
                    "sparse": "BM25 token weights",
                },
                index_path=str(self.index_path),
                status="empty",
            )

        info = self.client.get_collection(self.collection_name)
        total_count = info.points_count or 0

        if total_count == 0:
            return IndexStatsReport(
                total_operations=0,
                unique_specifications=0,
                specifications=[],
                vector_dimensions={
                    "dense": f"{DENSE_VECTOR_SIZE} (Cosine)",
                    "sparse": "BM25 token weights",
                },
                index_path=str(self.index_path),
                status="empty",
            )

        # Scroll all points to group by (source_title, source_version)
        specs_map: dict[tuple[str, str], int] = {}
        offset = None
        while True:
            records, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=250,
                offset=offset,
                with_payload=["source_title", "source_version"],
                with_vectors=False,
            )
            for rec in records:
                payload = rec.payload or {}
                title = payload.get("source_title", "Unknown")
                version = payload.get("source_version", "0.0.0")
                key = (title, version)
                specs_map[key] = specs_map.get(key, 0) + 1

            if offset is None:
                break

        specs_breakdown = [
            SpecStatBreakdown(
                source_title=title,
                source_version=version,
                chunk_count=count,
            )
            for (title, version), count in sorted(specs_map.items())
        ]

        return IndexStatsReport(
            total_operations=total_count,
            unique_specifications=len(specs_breakdown),
            specifications=specs_breakdown,
            vector_dimensions={
                "dense": f"{DENSE_VECTOR_SIZE} (Cosine)",
                "sparse": "BM25 token weights",
            },
            index_path=str(self.index_path),
            status="healthy",
        )


def index_chunk_stream(
    lines: Iterable[str],
    index_path: Path | str,
    embedder: Any = None,
) -> tuple[int, list[tuple[str, str]], str]:
    """Parse JSONL lines, synthesize text, compute vectors, and atomically commit to Qdrant.

    Parameters
    ----------
    lines : Iterable[str]
        Iterable of raw JSONL strings.
    index_path : Path | str
        Path to local Qdrant on-disk directory or ':memory:'.
    embedder : FastEmbedEngine | None
        Embedder instance. If None, initialized with defaults.

    Returns
    -------
    tuple[int, list[tuple[str, str]], str]
        (total_indexed, unique_specifications, generation_id)
    """
    import json
    from collections import OrderedDict

    from specprobe.chunker.models import OperationChunk
    from specprobe.index.embedder import FastEmbedEngine
    from specprobe.index.synthesizer import build_embedding_text

    if embedder is None:
        embedder = FastEmbedEngine()

    generation_id = str(uuid.uuid4())

    # Parse and validate chunks, deduplicating within the batch
    deduped_chunks: OrderedDict[tuple[str, str, str], tuple[OperationChunk, dict[str, Any]]] = (
        OrderedDict()
    )

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            raw_data = json.loads(line)
            chunk = OperationChunk.model_validate(raw_data)
        except Exception as exc:
            raise ValueError(f"Line {line_number}: invalid JSONL operation chunk: {exc}") from exc

        key = (
            chunk.metadata.source_title,
            chunk.metadata.source_version,
            chunk.metadata.operationId,
        )
        deduped_chunks[key] = (chunk, raw_data)

    if not deduped_chunks:
        return 0, [], generation_id

    # Build embedding texts and points
    texts: list[str] = []
    chunk_items = list(deduped_chunks.values())

    for chunk, _ in chunk_items:
        text = build_embedding_text(chunk)
        texts.append(text)

    dense_vectors = embedder.embed_dense(texts)
    sparse_vectors = embedder.embed_sparse(texts)

    points: list[models.PointStruct] = []
    unique_specs: set[tuple[str, str]] = set()

    for idx, (chunk, raw_data) in enumerate(chunk_items):
        meta = chunk.metadata
        op = chunk.operation
        source_title = meta.source_title
        source_version = meta.source_version
        op_id = meta.operationId
        unique_specs.add((source_title, source_version))

        sparse_indices, sparse_values = sparse_vectors[idx]
        pt_id = get_point_id(source_title, source_version, op_id)

        points.append(
            models.PointStruct(
                id=pt_id,
                vector={
                    DENSE_VECTOR_NAME: dense_vectors[idx],
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                },
                payload={
                    "source_title": source_title,
                    "source_version": source_version,
                    "operation_id": op_id,
                    "path": meta.path,
                    "method": meta.method.upper(),
                    "tags": op.get("tags") or meta.tags or [],
                    "deprecated": meta.deprecated,
                    "summary": op.get("summary"),
                    "embedding_text": texts[idx],
                    "generation_id": generation_id,
                    "raw_chunk": raw_data,
                },
            )
        )
    # Upsert all points and atomically purge older generations
    with QdrantIndexStore(index_path=index_path) as store:
        store.upsert_points(points)
        for title, version in unique_specs:
            store.delete_prior_generations(title, version, generation_id)

    return len(points), sorted(unique_specs), generation_id
