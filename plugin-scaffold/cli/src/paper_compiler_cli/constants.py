"""Internal pipeline constants (Phase 8 cleanup).

These were tunable knobs in v0.2 ``config.py`` but the v0.2 audit found
nobody touched them. They're documented here as internals so the user-
facing ``paper-compiler.toml`` stays small (~20 lines instead of ~40).

If a constant here turns out to actually need tuning per project, promote
it back into ``config.py`` with a deliberate dataclass field. Don't add
fields to ``config.py`` just because they exist somewhere in the code —
that's how the v0.2 sprawl happened.
"""

from __future__ import annotations

# ---- chunking (graph_db._chunk_paragraphs + text_utils.split_with_overlap) ----
# Target window per chunk in characters. Tuned to ~150 tokens for bge-small.
CHUNK_TARGET_CHARS = 750
# Overlap between adjacent chunks so cross-window sentences stay readable.
CHUNK_OVERLAP_CHARS = 200

# ---- retrieval (server/db.py:query_chunks) ----
# Default per-chunk preview length when full=False.
SNIPPET_CHARS = 240
# BM25 over-sampling factor before dense + diversification rerank.
BM25_OVERSAMPLE = 3
# Default chunk cap per paper in diversified output.
DEFAULT_MAX_PER_PAPER = 2

# ---- embeddings ----
# Embedding model — must match chunks_vec / atoms_vec / communities_vec dim.
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# ---- community detection (communities.py) ----
# Louvain resolution; > 1 prevents collapse into a single mega-cluster.
LOUVAIN_RESOLUTION = 1.4
# RNG seed so community ids are stable across rebuilds of the same corpus.
LOUVAIN_SEED = 42
# Min community size — singletons are dropped from the report and DB.
MIN_COMMUNITY_SIZE = 2
