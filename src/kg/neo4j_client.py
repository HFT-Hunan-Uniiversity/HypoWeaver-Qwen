# ============================================================================
# Neo4j 写入层 — src/kg/neo4j_client.py
# ============================================================================
# Neo4j 驱动的封装，负责：
#   1. 连接池管理（单例模式，全局复用）
#   2. 启动时建唯一索引（幂等，可重复运行）
#   3. MERGE 去重写入节点 + 关系（批量事务）
#   4. 健康检查与连接断开重连
#   5. 断点续跑的 doc_id 查询（已写入的论文跳过）
#
# 设计原则：
#   - 绝不抛异常到上层；所有写操作封装为 (ok, msg) 或 bool 返回值
#   - 每笔事务的上限由 config.NEO4J_BATCH_SIZE 控制
#   - 关系边属性统一挂载 evidence/source_doc/snippet/page，不建关系节点
# ============================================================================

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

from neo4j import GraphDatabase, Session

from src.kg.config import (
    NEO4J_BATCH_SIZE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_REQUIRED,
)
from src.kg.entities import (
    AuthorNode,
    ConceptNode,
    ConceptRelation,
    DatasetNode,
    KnowledgeGraph,
    MethodNode,
    PaperNode,
    RelationKind,
)


# ============================================================================
# 唯一索引约束（Cypher）
# ============================================================================
_UNIQUE_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Paper)     REQUIRE n.doc_id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Author)    REQUIRE n.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept)   REQUIRE n.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Method)    REQUIRE n.name   IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Dataset)   REQUIRE n.name   IS UNIQUE",
]

# 索引（非唯一，但加速查询）
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (n:Paper)   ON (n.year)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Concept) ON (n.alias_of)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Method)  ON (n.category)",
]


# ============================================================================
# 客户端
# ============================================================================
class Neo4jClient:
    """Neo4j 数据库操作封装。"""

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
        batch_size: int = NEO4J_BATCH_SIZE,
    ):
        self._uri = uri
        self._user = user
        self._password = password
        self._batch_size = batch_size
        self._driver = None

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """建立连接池，并在连接成功时创建约束与索引。"""
        try:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                max_connection_lifetime=3600,
                connection_acquisition_timeout=30,
            )
            # 验证连接
            self._driver.verify_connectivity()
            self._ensure_schema()
            return True
        except Exception as e:
            self._driver = None
            if NEO4J_REQUIRED:
                print(f"  ❌ Neo4j 连接失败: {e}")
            else:
                print(f"  ⚠️  Neo4j 连接失败（非强制）: {e}")
            return False

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    @property
    def is_connected(self) -> bool:
        try:
            if self._driver:
                self._driver.verify_connectivity()
                return True
        except Exception:
            pass
        return False

    def _ensure_schema(self) -> None:
        """幂等地创建唯一约束与索引。"""
        with self._driver.session(database="neo4j") as session:
            for cypher in _UNIQUE_CONSTRAINTS + _INDEXES:
                try:
                    session.run(cypher)
                except Exception as e:
                    print(f"  ⚠️  约束/索引创建警告: {e}")

    # ------------------------------------------------------------------
    # 断点续跑：查询已写入 doc_id
    # ------------------------------------------------------------------
    def list_written_doc_ids(self) -> Set[str]:
        """返回已存在 Paper 节点的 doc_id 集合（用于跳过已处理的论文）。"""
        if not self._driver:
            return set()
        try:
            with self._driver.session(database="neo4j") as session:
                result = session.run("MATCH (p:Paper) RETURN p.doc_id AS doc_id")
                return {r["doc_id"] for r in result if r["doc_id"]}
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # 写入单个 KnowledgeGraph（批量事务内）
    # ------------------------------------------------------------------
    def write_kg(self, kg: KnowledgeGraph) -> Tuple[bool, str]:
        """
        将 KnowledgeGraph 写入 Neo4j（单事务，内部含多个 MERGE）。
        返回 (成功标志, 消息)。
        """
        if not self._driver:
            return False, "Neo4j 未连接"

        try:
            with self._driver.session(database="neo4j") as session:
                self._merge_paper(session, kg.paper)
                self._merge_authors(session, kg.authors, kg.doc_id)
                self._merge_concepts(session, kg.concepts)
                self._merge_methods(session, kg.methods)
                self._merge_datasets(session, kg.datasets)
                self._merge_relations(session, kg.relations, kg.doc_id)
                self._link_paper_entities(session, kg)
            return True, "写入成功"
        except Exception as e:
            return False, f"写入失败: {e}"

    # ------------------------------------------------------------------
    # 内部 MERGE 方法（每个方法一个事务）
    # ------------------------------------------------------------------
    def _merge_paper(self, session: Session, node: PaperNode) -> None:
        props = node.model_dump(exclude={"metadata"}, exclude_none=True)
        meta = node.metadata
        session.run(
            """
            MERGE (p:Paper {doc_id: $doc_id})
            SET p += $props,
                p.title = $title,
                p.abstract = $abstract,
                p.journal = $journal,
                p.year = $year,
                p.doi = $doi,
                p.source_type = $source_type,
                p.updated_at = timestamp()
            """,
            doc_id=node.doc_id,
            title=node.title or "",
            abstract=node.abstract or "",
            journal=node.journal or "",
            year=node.year or "",
            doi=node.doi or "",
            source_type=node.source_type,
            props=props | meta,
        )

    def _merge_authors(
        self, session: Session, authors: List[AuthorNode], doc_id: str
    ) -> None:
        for batch in self._chunk(authors, self._batch_size):
            for a in batch:
                session.run(
                    """
                    MERGE (n:Author {name: $name})
                    """,
                    name=a.name,
                )

    def _merge_concepts(self, session: Session, concepts: List[ConceptNode]) -> None:
        for batch in self._chunk(concepts, self._batch_size):
            for c in batch:
                session.run(
                    """
                    MERGE (n:Concept {name: $name})
                    SET n.alias_of = $alias_of
                    """,
                    name=c.name,
                    alias_of=c.alias_of,
                )

    def _merge_methods(self, session: Session, methods: List[MethodNode]) -> None:
        for batch in self._chunk(methods, self._batch_size):
            for m in batch:
                session.run(
                    """
                    MERGE (n:Method {name: $name})
                    SET n.category = $category,
                        n.alias_of = $alias_of
                    """,
                    name=m.name,
                    category=m.category,
                    alias_of=m.alias_of,
                )

    def _merge_datasets(self, session: Session, datasets: List[DatasetNode]) -> None:
        for batch in self._chunk(datasets, self._batch_size):
            for d in batch:
                session.run(
                    """
                    MERGE (n:Dataset {name: $name})
                    SET n.alias_of = $alias_of
                    """,
                    name=d.name,
                    alias_of=d.alias_of,
                )

    def _merge_relations(
        self, session: Session, relations: List[ConceptRelation], doc_id: str
    ) -> None:
        """写入概念间关系边（因果 + 共现）。

        边属性挂载证据（evidence/source_doc/snippet/page），
        不建独立关系节点。
        """
        for batch in self._chunk(relations, self._batch_size):
            for r in batch:
                rel_type = r.relation.value
                session.run(
                    f"""
                    MATCH (a:Concept {{name: $source}})
                    MATCH (b:Concept {{name: $target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r.evidence = $evidence,
                        r.source_doc = $source_doc,
                        r.snippet = $snippet,
                        r.page = $page,
                        r.confidence = $confidence,
                        r.updated_at = timestamp()
                    """,
                    source=r.source,
                    target=r.target,
                    evidence=r.evidence.evidence,
                    source_doc=r.evidence.source_doc,
                    snippet=r.evidence.snippet,
                    page=r.evidence.page,
                    confidence=r.confidence,
                )

    def _link_paper_entities(self, session: Session, kg: KnowledgeGraph) -> None:
        """创建 Paper 到 Author/Concept/Method/Dataset 的固定关系。"""
        doc_id = kg.doc_id

        # Paper -[:AUTHORED_BY]-> Author
        for a in kg.authors:
            session.run(
                """
                MATCH (p:Paper {doc_id: $doc_id})
                MATCH (n:Author {name: $name})
                MERGE (p)-[:AUTHORED_BY]->(n)
                """,
                doc_id=doc_id,
                name=a.name,
            )

        # Paper -[:MENTIONS]-> Concept
        for c in kg.concepts:
            session.run(
                """
                MATCH (p:Paper {doc_id: $doc_id})
                MATCH (n:Concept {name: $name})
                MERGE (p)-[:MENTIONS]->(n)
                """,
                doc_id=doc_id,
                name=c.name,
            )

        # Paper -[:USES_METHOD]-> Method
        for m in kg.methods:
            session.run(
                """
                MATCH (p:Paper {doc_id: $doc_id})
                MATCH (n:Method {name: $name})
                MERGE (p)-[:USES_METHOD]->(n)
                """,
                doc_id=doc_id,
                name=m.name,
            )

        # Paper -[:USES_DATASET]-> Dataset
        for d in kg.datasets:
            session.run(
                """
                MATCH (p:Paper {doc_id: $doc_id})
                MATCH (n:Dataset {name: $name})
                MERGE (p)-[:USES_DATASET]->(n)
                """,
                doc_id=doc_id,
                name=d.name,
            )

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _chunk(items: list, size: int):
        for i in range(0, len(items), size):
            yield items[i : i + size]