from agent.memory.storage import MemoryChunk, MemoryStorage
from agent.memory.vector_backend import (
    SQLiteVectorBackend,
    VectorBackend,
    VectorMatch,
    VectorRecord,
)


def _chunk(
    chunk_id,
    embedding,
    *,
    path="memory/shared/test.md",
    scope="shared",
    user_id=None,
):
    return MemoryChunk(
        id=chunk_id,
        user_id=user_id,
        scope=scope,
        source="memory",
        path=path,
        start_line=1,
        end_line=1,
        text=f"text for {chunk_id}",
        embedding=embedding,
        hash=f"hash-{chunk_id}",
        metadata={"kind": "note"},
    )


def test_sqlite_vector_backend_preserves_filtering_and_score_order(tmp_path):
    storage = MemoryStorage(tmp_path / "index.db")
    assert isinstance(storage.vector_backend, SQLiteVectorBackend)
    storage.save_chunks_batch(
        [
            _chunk("shared-best", [1.0, 0.0]),
            _chunk("shared-second", [0.8, 0.2]),
            _chunk(
                "other-user",
                [1.0, 0.0],
                path="memory/users/other/test.md",
                scope="user",
                user_id="other",
            ),
        ]
    )

    results = storage.search_vector(
        [1.0, 0.0],
        user_id="current",
        scopes=["shared", "user"],
        limit=10,
    )

    assert [result.path for result in results] == [
        "memory/shared/test.md",
        "memory/shared/test.md",
    ]
    assert results[0].score > results[1].score
    assert storage.get_chunk("shared-best").embedding == [1.0, 0.0]
    storage.close()


class RecordingVectorBackend(VectorBackend):
    def __init__(self):
        self.upserted = []
        self.deleted = []
        self.search_filter = None

    def upsert(self, records):
        self.upserted.extend(records)

    def delete(self, ids=None, metadata_filter=None):
        self.deleted.append((ids, metadata_filter))

    def search(self, query_embedding, limit=10, metadata_filter=None):
        self.search_filter = metadata_filter
        return [
            VectorMatch(
                id="custom-result",
                score=0.75,
                metadata={
                    "path": "memory/shared/custom.md",
                    "start_line": 3,
                    "end_line": 4,
                    "text": "custom backend text",
                    "source": "memory",
                    "user_id": None,
                },
            )
        ]


def test_memory_storage_routes_vector_operations_through_backend(tmp_path):
    backend = RecordingVectorBackend()
    storage = MemoryStorage(tmp_path / "index.db", vector_backend=backend)
    chunk = _chunk("custom-result", [0.5, 0.5], path="memory/shared/custom.md")

    storage.save_chunk(chunk)
    results = storage.search_vector(
        [0.5, 0.5],
        user_id="current",
        scopes=["shared", "user"],
        limit=4,
    )
    storage.delete_by_path(chunk.path)

    assert backend.upserted == [
        VectorRecord(
            id="custom-result",
            embedding=[0.5, 0.5],
            metadata={
                "user_id": None,
                "scope": "shared",
                "source": "memory",
                "path": "memory/shared/custom.md",
                "start_line": 1,
                "end_line": 1,
                "text": "text for custom-result",
                "metadata": {"kind": "note"},
            },
        )
    ]
    assert backend.search_filter == {
        "scopes": ["shared", "user"],
        "user_id": "current",
    }
    assert backend.deleted == [(None, {"path": "memory/shared/custom.md"})]
    assert results[0].path == "memory/shared/custom.md"
    assert results[0].score == 0.75
    storage.close()
