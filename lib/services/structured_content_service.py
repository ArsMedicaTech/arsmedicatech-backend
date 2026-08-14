"""
Structured content storage and discovery service.

This service replaces the legacy ``custom_content`` microservice with a
SurrealDB-backed store and supports three discovery modes:

1. Browse clusters / tagged lists
2. Typesense text search (proxied)
3. k-NN semantic similarity using the caller's OpenAI key

Record shape and derived-field invariants are documented in
``STRUCTURED_CONTENT_SPEC.md``.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

import requests
from openai import AsyncOpenAI

from amt_nano.db.surreal import AsyncDbController
from lib.services.openai_security import OpenAISecurityService
from settings import (
    MIGRATION_OPENAI_API_KEY,
    SURREALDB_DATABASE,
    SURREALDB_NAMESPACE,
    TYPESENSE_API_KEY,
    TYPESENSE_STRUCTURED_CONTENT_ALIAS,
    TYPESENSE_URL,
    logger,
)

DEFAULT_EMBED_MODEL = "text-embedding-3-small"
TABLE_NAME = "structured_content"
DEFAULT_NAMESPACE = "arsmedicatech"
DEFAULT_DATABASE = "patients"
EMBEDDING_DIMENSION = 1536

# Schema for the structured_content table.  Mirrors the HNSW index definition
# used by ``amt_nano.db.vec`` but adds the authored fields required by this
# feature.  ``PERMISSIONS NONE`` keeps the table write-only through this module.
_SCHEMA_SQL = """
USE ns {ns} DB {db};

DEFINE TABLE {table} SCHEMAFULL PERMISSIONS NONE;

DEFINE FIELD scope ON {table} TYPE string DEFAULT 'global' ASSERT $value == 'global';
DEFINE FIELD title ON {table} TYPE string;
DEFINE FIELD tags ON {table} TYPE array<string> DEFAULT [];
DEFINE FIELD cluster ON {table} TYPE string;
DEFINE FIELD content ON {table} FLEXIBLE TYPE object;
DEFINE FIELD content.nodes ON {table} TYPE array;
DEFINE FIELD plain_text ON {table} TYPE option<string>;
DEFINE FIELD embedding ON {table} TYPE option<array<float>>
    ASSERT array::len($value) = {dim};
DEFINE FIELD embed_model ON {table} TYPE option<string>;
DEFINE FIELD content_hash ON {table} TYPE option<string>;
DEFINE FIELD created_at ON {table} TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON {table} TYPE datetime VALUE time::now();

DEFINE INDEX idx_cluster ON {table} FIELDS cluster;
DEFINE INDEX idx_scope ON {table} FIELDS scope;
DEFINE INDEX idx_tags ON {table} FIELDS tags;
DEFINE INDEX idx_embedding ON {table}
    FIELDS embedding
    HNSW DIMENSION {dim} DIST COSINE TYPE F64;
"""


def _canonical_json(obj: Any) -> str:
    """Return a stable, compact JSON representation for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _extract_title(nodes: List[Dict[str, Any]]) -> str:
    """Return the text of the first title node, or an empty string."""
    for node in nodes:
        if node.get("type") == "title":
            text = node.get("text")
            if isinstance(text, str):
                return text
    return ""


def _derive_plain_text(nodes: List[Dict[str, Any]]) -> str:
    """Render a plain-text indexable form of ``content.nodes``."""
    sections: List[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type in ("title", "paragraph"):
            text = node.get("text")
            if isinstance(text, str) and text:
                sections.append(text)
        elif node_type == "list":
            items = node.get("items", [])
            if isinstance(items, list):
                bullets = [f"- {item}" for item in items if isinstance(item, str) and item]
                if bullets:
                    sections.append("\n".join(bullets))
    return "\n\n".join(sections)


def _content_hash(nodes: List[Dict[str, Any]]) -> str:
    """Compute the canonical SHA-256 hash of ``content.nodes``."""
    digest = hashlib.sha256(_canonical_json(nodes).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _preview_text(plain_text: str, max_length: int = 200) -> str:
    """Return a compact preview suitable for list responses."""
    collapsed = re.sub(r"\s+", " ", plain_text or "").strip()
    if len(collapsed) <= max_length:
        return collapsed
    return collapsed[: max_length - 3].rstrip() + "..."


def _record_id_to_str(record_id: Any) -> str:
    """Best-effort conversion of a SurrealDB record id to a string."""
    if isinstance(record_id, str):
        return record_id
    if hasattr(record_id, "__str__"):
        return str(record_id)
    return ""


def _list_item(record: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a full structured_content record to the public list shape."""
    return {
        "id": _record_id_to_str(record.get("id")),
        "title": record.get("title", "") or _extract_title(record.get("content", {}).get("nodes", [])),
        "tags": record.get("tags", []) or [],
        "preview": _preview_text(record.get("plain_text", "")),
    }


class StructuredContentService:
    """
    Storage and discovery service for structured patient-education content.

    The service owns the sole write path for ``content.nodes`` and its derived
    fields (``plain_text``, ``embedding``, ``content_hash``).  All other writes
    should use the helper methods provided here so the derived-field invariant
    is preserved.
    """

    def __init__(
        self,
        db_controller: Optional[Any] = None,
        openai_security_service: Optional[OpenAISecurityService] = None,
        typesense_url: Optional[str] = None,
        typesense_api_key: Optional[str] = None,
        typesense_alias: Optional[str] = None,
        namespace: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        """
        Initialize the service.

        :param db_controller: Optional SurrealDB controller.  Defaults to an
            ``AsyncDbController`` using the configured namespace/database.
        :param openai_security_service: Optional ``OpenAISecurityService`` for
            validating and retrieving per-user OpenAI keys.
        :param typesense_url: Optional Typesense base URL override.
        :param typesense_api_key: Optional Typesense API key override.
        :param typesense_alias: Optional Typesense collection alias override.
        :param namespace: Optional SurrealDB namespace override.
        :param database: Optional SurrealDB database override.
        """
        self.namespace = namespace or SURREALDB_NAMESPACE or DEFAULT_NAMESPACE
        self.database = database or SURREALDB_DATABASE or DEFAULT_DATABASE
        self.db = db_controller or AsyncDbController(
            namespace=self.namespace,
            database=self.database,
        )
        self.openai_security = openai_security_service or OpenAISecurityService()
        self.typesense_url = (
            typesense_url if typesense_url is not None else (TYPESENSE_URL or "")
        ).rstrip("/")
        self.typesense_key = (
            typesense_api_key
            if typesense_api_key is not None
            else (TYPESENSE_API_KEY or "")
        )
        self.typesense_alias = (
            typesense_alias
            if typesense_alias is not None
            else (TYPESENSE_STRUCTURED_CONTENT_ALIAS or "structured_content")
        )
        self.embed_model = DEFAULT_EMBED_MODEL

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def init_schema(self) -> None:
        """Create the ``structured_content`` table and indexes if missing."""
        await self.db.connect()
        try:
            sql = _SCHEMA_SQL.format(
                ns=self.namespace,
                db=self.database,
                table=TABLE_NAME,
                dim=EMBEDDING_DIMENSION,
            )
            await self.db.query(sql)
            logger.info("Initialized structured_content schema.")
        finally:
            await self.db.close()

    # ------------------------------------------------------------------
    # Core reads
    # ------------------------------------------------------------------

    async def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Return a full structured_content record by id."""
        await self.db.connect()
        try:
            # Normalize id to the record-local portion to avoid double prefixes.
            local_id = item_id.split(":")[-1]
            result = await self.db.select(f"{TABLE_NAME}:{local_id}")
            if isinstance(result, list):
                result = result[0] if result else None
            if not isinstance(result, dict):
                return None
            result["id"] = _record_id_to_str(result.get("id", f"{TABLE_NAME}:{local_id}"))
            return result
        finally:
            await self.db.close()

    async def list_clusters(self) -> List[Dict[str, Any]]:
        """Return cluster names with item counts, ordered alphabetically."""
        await self.db.connect()
        try:
            result = await self.db.query(
                f"SELECT cluster, count() AS count FROM {TABLE_NAME} "
                f"WHERE scope = 'global' GROUP BY cluster ORDER BY cluster ASC;"
            )
            if not isinstance(result, list):
                return []
            rows = [
                {"cluster": row.get("cluster"), "count": row.get("count", 0)}
                for row in result
                if isinstance(row, dict) and row.get("cluster")
            ]
            return rows
        finally:
            await self.db.close()

    async def list_items(
        self,
        cluster: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return list items filtered by cluster and/or tags."""
        filters = ["scope = 'global'"]
        params: Dict[str, Any] = {}
        if cluster:
            filters.append("cluster = $cluster")
            params["cluster"] = cluster
        if tags:
            # Match records whose tags contain all requested tags.
            filters.append("tags CONTAINSALL $tags")
            params["tags"] = tags

        where_clause = " AND ".join(filters)
        await self.db.connect()
        try:
            result = await self.db.query(
                f"SELECT * FROM {TABLE_NAME} WHERE {where_clause} ORDER BY title ASC;",
                params,
            )
            if not isinstance(result, list):
                return []
            return [_list_item(row) for row in result if isinstance(row, dict)]
        finally:
            await self.db.close()

    # ------------------------------------------------------------------
    # Mode 2: Typesense search
    # ------------------------------------------------------------------

    async def search(self, query: str) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Proxy a text search to Typesense.

        :return: A tuple of (items, is_available).  When Typesense is
            unreachable the list is empty and ``is_available`` is ``False``.
        """
        if not self.typesense_url or not self.typesense_key:
            logger.warning("Typesense is not configured for structured content search.")
            return [], False

        headers = {
            "X-TYPESENSE-API-KEY": self.typesense_key,
            "Content-Type": "application/json",
        }
        params = {
            "q": query,
            "query_by": "title,plain_text,tags",
            "filter_by": "scope:=global",
            "per_page": 50,
        }
        try:
            url = f"{self.typesense_url}/collections/{self.typesense_alias}/documents/search"
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(f"Typesense search unavailable: {exc}")
            return [], False

        data = response.json()
        hits = data.get("hits", []) if isinstance(data, dict) else []
        items: List[Dict[str, Any]] = []
        for hit in hits:
            document = hit.get("document", {}) if isinstance(hit, dict) else {}
            if not isinstance(document, dict):
                continue
            record = {
                "id": document.get("id", ""),
                "title": document.get("title", ""),
                "tags": document.get("tags", []),
                "preview": _preview_text(document.get("plain_text", "")),
            }
            items.append(record)
        return items, True

    # ------------------------------------------------------------------
    # Mode 3: semantic similarity
    # ------------------------------------------------------------------

    async def similar(
        self, query: str, user_id: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Return k-NN results for a query embedding generated with the user's key.

        :return: A tuple of (items, error_message).  ``error_message`` is set when
            no key is configured (matching the V12 string) or the corpus model
            mismatches the model used to embed the query.
        """
        api_key, error = self.openai_security.get_user_api_key_with_validation(
            str(user_id)
        )
        if not api_key:
            # Preserve the exact message the Flutter client already surfaces.
            return [], error or "OpenAI API key not configured."

        client = AsyncOpenAI(api_key=api_key)
        try:
            qvec = await self._embed_one(client, query)
        except Exception as exc:
            logger.error(f"Failed to embed query for user={user_id}: {exc}")
            return [], "OpenAI embedding request failed."

        await self.db.connect()
        try:
            # Verify the corpus was built with the same model.  Querying a
            # differently-sized vector dimension is also rejected implicitly by
            # the index, but checking the model name gives a clearer failure.
            meta_result = await self.db.query(
                f"SELECT embed_model FROM {TABLE_NAME} WHERE scope = 'global' "
                f"AND embedding IS NOT NONE LIMIT 1;"
            )
            if isinstance(meta_result, list) and meta_result:
                meta_row = meta_result[0]
                if isinstance(meta_row, dict):
                    corpus_model = meta_row.get("embed_model")
                    if corpus_model and corpus_model != self.embed_model:
                        logger.error(
                            f"Embedding model mismatch: corpus={corpus_model}, "
                            f"query={self.embed_model}"
                        )
                        return [], "Embedding model mismatch. Please reindex content."

            result = await self.db.query(
                f"SELECT id, title, tags, plain_text FROM {TABLE_NAME} "
                f"WHERE scope = 'global' AND embedding <|4, COSINE|> $vec;",
                {"vec": qvec},
            )
            if not isinstance(result, list):
                return [], None
            items = []
            for row in result:
                if isinstance(row, dict):
                    row["id"] = _record_id_to_str(row.get("id", ""))
                    items.append(_list_item(row))
            return items, None
        finally:
            await self.db.close()

    async def _embed_one(self, client: AsyncOpenAI, text: str) -> List[float]:
        """Embed a single string with the configured model."""
        resp = await client.embeddings.create(model=self.embed_model, input=[text])
        return cast(List[float], resp.data[0].embedding)

    # ------------------------------------------------------------------
    # Write path (sole writer of content.nodes + derived fields)
    # ------------------------------------------------------------------

    async def _derive_and_save(
        self,
        local_id: str,
        content: Dict[str, Any],
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        cluster: Optional[str] = None,
        scope: str = "global",
    ) -> Dict[str, Any]:
        """
        Save content and regenerate all derived fields together.

        This is the only method that should write ``content.nodes`` directly.
        """
        nodes = content.get("nodes", []) if isinstance(content, dict) else []
        plain_text = _derive_plain_text(nodes)
        content_hash = _content_hash(nodes)
        payload: Dict[str, Any] = {
            "content": content,
            "plain_text": plain_text,
            "content_hash": content_hash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if title is not None:
            payload["title"] = title
        if tags is not None:
            payload["tags"] = tags
        if cluster is not None:
            payload["cluster"] = cluster
        if scope:
            payload["scope"] = scope

        await self.db.connect()
        try:
            await self.db.query(
                f"UPDATE {TABLE_NAME}:{local_id} MERGE $data;",
                {"data": payload},
            )
            return payload
        finally:
            await self.db.close()

    async def create_or_update_item(
        self,
        local_id: str,
        content: Dict[str, Any],
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or replace an authored item and its derived fields."""
        nodes = content.get("nodes", []) if isinstance(content, dict) else []
        record_title = title or _extract_title(nodes)
        record_tags = tags or []
        record_cluster = cluster or (record_tags[0] if record_tags else "general")
        plain_text = _derive_plain_text(nodes)
        content_hash = _content_hash(nodes)

        record: Dict[str, Any] = {
            "id": local_id,
            "scope": "global",
            "title": record_title,
            "tags": record_tags,
            "cluster": record_cluster,
            "content": content,
            "plain_text": plain_text,
            "content_hash": content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.db.connect()
        try:
            await self.db.query(
                f"INSERT INTO {TABLE_NAME} $data ON DUPLICATE KEY UPDATE "
                f"scope = $value.scope, title = $value.title, tags = $value.tags, "
                f"cluster = $value.cluster, content = $value.content, "
                f"plain_text = $value.plain_text, content_hash = $value.content_hash, "
                f"updated_at = $value.updated_at;",
                {"data": record},
            )
        finally:
            await self.db.close()
        return record

    async def update_title_only(
        self, local_id: str, title: str
    ) -> Optional[Dict[str, Any]]:
        """
        Update the title without touching derived fields.

        Used by tests and any future authoring endpoint that edits metadata only.
        """
        await self.db.connect()
        try:
            await self.db.query(
                f"UPDATE {TABLE_NAME}:{local_id} MERGE $data;",
                {"data": {"title": title, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
        finally:
            await self.db.close()
        return await self.get_item(local_id)

    # ------------------------------------------------------------------
    # Ingest / reindex
    # ------------------------------------------------------------------

    async def ingest_from_legacy(
        self, source_path: str, embed: bool = False
    ) -> Dict[str, Any]:
        """
        Import authored content from a legacy ``data.json`` file.

        Maps the legacy ``tags`` field onto ``cluster`` while preserving ``tags``,
        drops ``user_id``, and seeds ``content.nodes`` plus derived fields.

        :param source_path: Path to the legacy ``custom_content/data.json`` file.
        :param embed: If ``True``, embed imported items immediately using the
            migration key.  Defaults to ``False`` so reindex can run separately.
        :return: Summary of records imported.
        """
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else [data]
        imported: List[str] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            legacy_id = item.get("id") or item.get("content_id")
            if not legacy_id:
                logger.warning("Skipping legacy item without an id.")
                continue

            tags = item.get("tags", [])
            if not isinstance(tags, list):
                tags = [str(tags)]
            cluster = item.get("cluster") or (tags[0] if tags else "general")
            content = item.get("content", {"nodes": []})
            if not isinstance(content, dict):
                content = {"nodes": []}

            await self.create_or_update_item(
                local_id=str(legacy_id),
                content=content,
                title=item.get("title"),
                tags=tags,
                cluster=cluster,
            )
            imported.append(str(legacy_id))

        summary = {"imported": len(imported), "ids": imported}
        if embed and imported:
            reindex_summary = await self.reindex()
            summary["reindex"] = reindex_summary
        return summary

    async def reindex(self) -> Dict[str, Any]:
        """
        Re-derive and embed stale records, then publish to Typesense.

        This is the only operation that should write ``plain_text``, ``embedding``,
        and ``content_hash``.

        :return: Summary dict with counts of embedded records, skipped records,
            and Typesense collection names.
        """
        migration_client = AsyncOpenAI(api_key=MIGRATION_OPENAI_API_KEY)
        await self.db.connect()
        try:
            result = await self.db.query(
                f"SELECT * FROM {TABLE_NAME} WHERE scope = 'global';"
            )
            records = [r for r in result if isinstance(r, dict)] if isinstance(result, list) else []
        finally:
            await self.db.close()

        to_embed: List[Dict[str, Any]] = []
        skipped = 0
        for record in records:
            nodes = record.get("content", {}).get("nodes", [])
            current_hash = _content_hash(nodes)
            current_model = record.get("embed_model")
            if record.get("content_hash") == current_hash and current_model == self.embed_model:
                skipped += 1
                continue
            plain_text = _derive_plain_text(nodes)
            to_embed.append({
                "id": _record_id_to_str(record.get("id")),
                "plain_text": plain_text,
                "content_hash": current_hash,
            })

        embedded = 0
        for i in range(0, len(to_embed), 96):
            batch = to_embed[i : i + 96]
            texts = [b["plain_text"] for b in batch]
            try:
                resp = await migration_client.embeddings.create(
                    model=self.embed_model, input=texts
                )
            except Exception as exc:
                logger.error(f"Failed to embed batch during reindex: {exc}")
                raise

            await self.db.connect()
            try:
                for b, embedding in zip(batch, resp.data):
                    local_id = b["id"].split(":")[-1]
                    await self.db.query(
                        f"UPDATE {TABLE_NAME}:{local_id} MERGE $data;",
                        {
                            "data": {
                                "plain_text": b["plain_text"],
                                "embedding": embedding.embedding,
                                "content_hash": b["content_hash"],
                                "embed_model": self.embed_model,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
            finally:
                await self.db.close()
            embedded += len(batch)

        # Re-fetch fully populated records for Typesense.
        await self.db.connect()
        try:
            result = await self.db.query(
                f"SELECT id, title, tags, cluster, scope, plain_text FROM {TABLE_NAME} "
                f"WHERE scope = 'global';"
            )
            docs = [r for r in result if isinstance(r, dict)] if isinstance(result, list) else []
        finally:
            await self.db.close()

        typesense_result = self._reindex_typesense(docs)

        return {
            "embedded": embedded,
            "skipped": skipped,
            "total": len(records),
            "typesense": typesense_result,
        }

    def _reindex_typesense(self, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Publish ``docs`` to a new Typesense collection and atomically swap the alias.

        Follows the versioned-collection + alias-swap pattern so a failed
        reindex never serves a half-built collection.  Old collections are left
        for manual retirement.
        """
        if not self.typesense_url or not self.typesense_key:
            logger.warning("Typesense not configured; skipping index publish.")
            return {"published": 0, "collection": None, "alias": None, "error": "Typesense not configured"}

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        collection_name = f"structured_content_{timestamp}"
        headers = {
            "X-TYPESENSE-API-KEY": self.typesense_key,
            "Content-Type": "application/json",
        }

        # 1. Create the versioned collection.
        schema = {
            "name": collection_name,
            "fields": [
                {"name": "id", "type": "string"},
                {"name": "title", "type": "string", "optional": True},
                {"name": "plain_text", "type": "string", "optional": True},
                {"name": "tags", "type": "string[]", "facet": True, "optional": True},
                {"name": "cluster", "type": "string", "facet": True, "optional": True},
                {"name": "scope", "type": "string", "facet": True, "optional": True},
            ],
            "default_sorting_field": "",
        }
        # Typesense rejects an empty default_sorting_field; omit it when unset.
        schema.pop("default_sorting_field")

        try:
            create_resp = requests.post(
                f"{self.typesense_url}/collections",
                headers=headers,
                json=schema,
                timeout=30,
            )
            create_resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(f"Failed to create Typesense collection {collection_name}: {exc}")
            return {"published": 0, "collection": collection_name, "error": str(exc)}

        # 2. Bulk import documents.
        import_lines = []
        for doc in docs:
            import_doc = {
                "id": _record_id_to_str(doc.get("id", "")),
                "title": doc.get("title", ""),
                "plain_text": doc.get("plain_text", ""),
                "tags": doc.get("tags", []) or [],
                "cluster": doc.get("cluster", ""),
                "scope": doc.get("scope", "global"),
            }
            import_lines.append(json.dumps(import_doc, ensure_ascii=False))

        published = 0
        if import_lines:
            try:
                import_resp = requests.post(
                    f"{self.typesense_url}/collections/{collection_name}/documents/import",
                    headers=headers,
                    params={"action": "create"},
                    data="\n".join(import_lines),
                    timeout=60,
                )
                import_resp.raise_for_status()
                for line in import_resp.text.strip().split("\n"):
                    if line:
                        try:
                            parsed = json.loads(line)
                            if parsed.get("success"):
                                published += 1
                        except json.JSONDecodeError:
                            pass
            except requests.RequestException as exc:
                logger.error(f"Failed to import documents into {collection_name}: {exc}")
                return {
                    "published": 0,
                    "collection": collection_name,
                    "error": str(exc),
                }

        # 3. Atomically point the alias to the new collection.
        try:
            alias_payload = {"collection_name": collection_name}
            alias_resp = requests.post(
                f"{self.typesense_url}/aliases",
                headers=headers,
                json=alias_payload,
                timeout=30,
            )
            if alias_resp.status_code == 409:
                requests.put(
                    f"{self.typesense_url}/aliases/{self.typesense_alias}",
                    headers=headers,
                    json=alias_payload,
                    timeout=30,
                ).raise_for_status()
            else:
                alias_resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error(f"Failed to swap Typesense alias {self.typesense_alias}: {exc}")
            return {
                "published": published,
                "collection": collection_name,
                "error": str(exc),
            }

        return {
            "published": published,
            "collection": collection_name,
            "alias": self.typesense_alias,
        }
