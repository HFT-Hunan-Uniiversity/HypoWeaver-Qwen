# ============================================================================
# 向量存储封装 — src/vector/store.py
# ============================================================================
# Chunk 向量存储层（hdf5 本地临时版 + 工厂函数）。
#
# 设计目标：
#   - 存储后端独立：上层 chunker / embedding 完全不用改动，
#     后续换成 pgvector 时只需重写本模块内部，接口保持不变。
#   - 接口：
#       VectorStoreH5(path)
#         .open()
#         .add(vectors, metadatas)          # 追加向量+元数据
#         .search(query_vec, top_k)         # 余弦 Top-K 检索，返回 [(score, meta)]
#         .count() / .close()
#         .get_meta(idx) / .all_metas()
#   - ID 生成：doc_id + chunk_id 作为元数据，全库唯一索引。
#   - 工厂：get_store() 按环境变量 VECTOR_BACKEND 切换后端（当前仅 hdf5）。
# ============================================================================

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import h5py
import numpy as np

_DEFAULT_STORE_PATH = "artifacts/vector/all_store.h5"


class VectorStoreH5:
    """
    基于 hdf5 的向量存储（本地磁盘，零外部服务依赖）。
    数据结构：
        /vectors       (N, dim) float32
        /metas         JSON 字符串数组 (N,)
        /doc_ids       (N,) 字符串数组
    """

    def __init__(self, path: str = None):
        self.path = str(path or _DEFAULT_STORE_PATH)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._h5 = None
        self._len = 0
        self._dims = 0
        self._meta_cache: Dict[int, dict] = {}

    # ---------------- 生命周期 ----------------
    def open(self) -> "VectorStoreH5":
        """打开 hdf5 文件（不存在则创建）。"""
        # 跨平台兼容：Windows 上关闭 hdf5 文件锁，避免 Linux→Windows 拷贝的文件锁冲突
        if os.name == "nt":
            os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
        self._h5 = h5py.File(self.path, "a")
        if "vectors" not in self._h5:
            self._h5.create_dataset("vectors", shape=(0, 512), maxshape=(None, 512),
                                    dtype=np.float32)
        if "metas" not in self._h5:
            self._h5.create_dataset("metas", shape=(0,), maxshape=(None,),
                                    dtype=h5py.string_dtype(encoding="utf-8"))
        self._len = self._h5["vectors"].shape[0]
        self._dims = self._h5["vectors"].shape[1]
        # 预加载全部 meta（chunk 级，量不大）
        if self._len:
            metas = self._h5["metas"][:]
            self._meta_cache = {i: json.loads(m) for i, m in enumerate(metas)}
        return self

    def close(self) -> None:
        if self._h5:
            self._h5.close()
            self._h5 = None

    # ---------------- 写入 ----------------
    def add(self, vectors: np.ndarray, metadatas: List[dict]) -> None:
        """追加向量 + 元数据列表。
        参数:
          vectors:    (N, dim) float32
          metadatas:  长度 N 的 dict 列表（含 doc_id / chunk_id / chunk_text 等）
        """
        if self._h5 is None:
            raise RuntimeError("store 未打开")
        if len(vectors) != len(metadatas):
            raise ValueError(f"向量数({len(vectors)})与元数据数({len(metadatas)})不一致")

        n = len(vectors)
        if n == 0:
            return
        dim = vectors.shape[1]
        vs = self._h5["vectors"]
        ms = self._h5["metas"]

        start = vs.shape[0]
        # 扩展数据集
        vs.resize((start + n, dim))
        ms.resize((start + n,))
        vs[start:start + n] = vectors.astype(np.float32)
        ms[start:start + n] = np.array(
            [json.dumps(m, ensure_ascii=False) for m in metadatas],
            dtype=h5py.string_dtype(encoding="utf-8"),
        )
        self._len = start + n
        self._dims = dim
        for i, m in enumerate(metadatas, start):
            self._meta_cache[i] = m

    # ---------------- 检索 ----------------
    def search(self, query_vec: np.ndarray, top_k: int = 5) -> List[Tuple[float, dict]]:
        """
        余弦相似度 Top-K 检索（暴力全扫描，小样本够用）。

        参数:
          query_vec:  (dim,) 查询向量
          top_k:      返回前 K 个

        返回:
          [(score, metadata), ...] 按相似度降序。
        """
        if self._len == 0:
            return []
        vs = self._h5["vectors"][:self._len]
        qv = query_vec.astype(np.float32).flatten()
        # 余弦 = 归一化后点积
        norms = np.linalg.norm(vs, axis=1)
        sims = (vs @ qv) / (norms * np.linalg.norm(qv) + 1e-8)
        k = min(top_k, self._len)
        idx = np.argsort(sims)[::-1][:k]
        return [(float(sims[i]), self._meta_cache.get(int(i), {})) for i in idx]

    def count(self) -> int:
        return self._len

    # ---------------- 元数据访问 ----------------
    def get_meta(self, idx: int) -> Optional[dict]:
        return self._meta_cache.get(idx)

    def all_metas(self) -> List[dict]:
        """返回全部元数据（供全量导出/统计）。"""
        return [self._meta_cache[i] for i in range(self._len)]

    # ---------------- 向量读取（供迁移/导出） ----------------
    def get_vec(self, idx: int) -> np.ndarray:
        """读取单条向量。"""
        return np.asarray(self._h5["vectors"][idx], dtype=np.float32)

    def get_batch(self, start: int, end: int) -> np.ndarray:
        """批量读取 [start, end) 的向量，返回 (n, dim) float32。"""
        return np.asarray(self._h5["vectors"][start:end], dtype=np.float32)


# ============================================================================
# 工厂函数 — 按环境变量 VECTOR_BACKEND 切换后端
# ============================================================================
def get_store(path: str = None, backend: str = None) -> VectorStoreH5:
    """
    返回向量存储实例（当前仅 hdf5 后端）。

    参数:
      path:    hdf5 文件路径（默认 artifacts/vector/all_store.h5）
      backend: 后端类型。'hdf5'（默认）；'qdrant' 预留未来切换。

    未来新增 Qdrant 后端时，只需实现与 VectorStoreH5 相同的接口
    （open/add/search/count/close），上层无需改动。
    """
    backend = backend or os.environ.get("VECTOR_BACKEND", "hdf5")
    if backend == "qdrant":
        # 预留：未来实现时返回 VectorStoreQdrant 实例
        raise NotImplementedError(
            "Qdrant 后端尚未实现，当前使用 hdf5 后端。"
            "迁移时需实现与 VectorStoreH5 相同的接口。"
        )
    return VectorStoreH5(path or _DEFAULT_STORE_PATH)


if __name__ == "__main__":
    # 冒烟测试
    store = get_store("artifacts/vector/smoke_store.h5").open()
    print(f"store 打开成功, count={store.count()}")
    store.close()
    print("✅ 冒烟测试通过")