# ============================================================================
# 嵌入适配器 — src/embedding.py
# ============================================================================
# 统一文本预处理 + 向量生成，全项目唯一入口。
#
# 设计：
#   - 模型: BAAI/bge-small-zh-v1.5（本地免费, CPU 可跑）
#   - 镜像: 默认 HF_ENDPOINT=https://hf-mirror.com（国内加速）
#   - 懒加载: 首次调用 embed 时加载模型（import 不阻塞）
#   - 兜底: 模型加载失败返回纯规则特征向量（零依赖），流程不中断
#   - 单接口: embed_texts(texts)->numpy.ndarray, 上层不感知底层实现
# ============================================================================

from __future__ import annotations

import hashlib
import os
import re
from typing import List, Optional

import numpy as np

# 国内镜像（模型下载走 hf-mirror）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
_DIM = 512  # bge-small-zh-v1.5 向量维度

# ModelScope 本地缓存目录（优先加载，避免走 hf-mirror）
_LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "models_cache",
    "models", "BAAI--bge-small-zh-v1.5", "snapshots", "master",
)

# 文本预处理
_WS = re.compile(r"\s+")
_JUNK = re.compile(r"[#*_`|>~()\[\]{}]")
_NUM = re.compile(r"[0-9]+")


def _preprocess(text: str) -> str:
    """统一文本预处理：去 markdown 符号、压缩空白、统一半角。"""
    if not text:
        return ""
    t = _JUNK.sub(" ", text)
    t = _WS.sub(" ", t)
    t = t.replace("，", ",").replace("。", ".").replace("；", ";").replace("：", ":")
    t = t.replace("（", "(").replace("）", ")").replace("“", '"').replace("”", '"')
    return t.strip()


class Embedder:
    """BGE 嵌入器（懒加载 + 规则兜底）。"""

    def __init__(self, model_name: str = _MODEL_NAME):
        self.model_name = model_name
        self._model: Optional[object] = None
        self._tokenizer = None
        self._load_error: Optional[str] = None

    # ---------------- 模型加载 ----------------
    def _load(self) -> bool:
        if self._model is not None:
            return True
        if self._load_error:
            return False
        try:
            from sentence_transformers import SentenceTransformer
            # 优先本地缓存（ModelScope 已下载）
            local = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "models_cache",
                "models", "BAAI--bge-small-zh-v1.5", "snapshots", "master",
            )
            if os.path.isdir(local):
                self._model = SentenceTransformer(local)
            else:
                self._model = SentenceTransformer(self.model_name)
            return True
        except Exception as e:
            self._load_error = str(e)
            print(f"⚠️  BGE 模型加载失败，降级为规则特征向量: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    # ---------------- 向量生成 ----------------
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        批量生成向量。

        参数:
          texts: 文本列表
          batch_size: 推理批大小（内存友好）

        返回:
          np.ndarray shape=(n, 512)；模型不可用时返回规则特征向量。
        """
        if not texts:
            return np.zeros((0, _DIM), dtype=np.float32)

        if self._load():
            try:
                vecs = self._model.encode(
                    [_preprocess(t) for t in texts],
                    batch_size=batch_size,
                    normalize_embeddings=True,   # 余弦相似度直接点积
                    show_progress_bar=False,
                )
                return np.asarray(vecs, dtype=np.float32)
            except Exception as e:
                print(f"⚠️  推理失败，降级: {e}")
                self._load_error = str(e)
                return self._rule_features(texts)

        return self._rule_features(texts)

    def embed(self, text: str) -> np.ndarray:
        """单文本向量。"""
        v = self.embed_texts([text])
        return v[0] if len(v) else np.zeros(_DIM, dtype=np.float32)

    # ---------------- 规则兜底（模型不可用） ----------------
    @staticmethod
    def _rule_features(texts: List[str]) -> np.ndarray:
        """字符 n-gram 哈希特征（临时兜底，可区分文本但不语义）。"""
        dim = _DIM
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            t = _preprocess(t).lower()
            # 单字符 + 双字符 n-gram 哈希
            grams = []
            for c in t:
                if c.strip():
                    grams.append(c)
            for j in range(len(t) - 1):
                if t[j:j + 2].strip():
                    grams.append(t[j:j + 2])
            for g in grams:
                h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16)
                out[i, h % dim] += 1.0
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out.astype(np.float32)


# 全局单例（懒加载）
_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """获取全局嵌入器（单例）。"""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def embed_texts(texts: List[str]) -> np.ndarray:
    """便捷入口: 批量向量化。"""
    return get_embedder().embed_texts(texts)


def embed(text: str) -> np.ndarray:
    """便捷入口: 单文本向量化。"""
    return get_embedder().embed(text)


def preprocess(text: str) -> str:
    """对外暴露文本预处理（供 chunker/prompt 使用）。"""
    return _preprocess(text)


if __name__ == "__main__":
    # 冒烟测试
    e = get_embedder()
    print(f"模型: {e.model_name} | ready={e.is_ready}")
    sent1 = "绿色金融政策促进了高耗能企业的绿色技术创新"
    sent2 = "ESG ratings and corporate sustainability performance"
    sent3 = "今天天气很好适合出去散步"
    vecs = e.embed_texts([sent1, sent2, sent3])
    print(f"向量 shape: {vecs.shape}")
    # 相似度自检：同类应该比异类高
    s12 = float(np.dot(vecs[0], vecs[1]))
    s13 = float(np.dot(vecs[0], vecs[2]))
    s23 = float(np.dot(vecs[1], vecs[2]))
    print(f"绿色金融 vs ESG: {s12:.3f} | 绿色金融 vs 天气: {s13:.3f} | ESG vs 天气: {s23:.3f}")