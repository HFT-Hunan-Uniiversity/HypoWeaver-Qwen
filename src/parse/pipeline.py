# B 阶段主流水线: PDF → MinerU → 清洗 → 元数据 → 索引
# 用法: python src/parse/pipeline.py run --pdf <pdf_path>
#       python src/parse/pipeline.py run --dir <pdf_dir>
#       python src/parse/pipeline.py index              # 构建 LlamaIndex 向量索引

import argparse, hashlib, json, os, sys, time
from pathlib import Path
from typing import Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.parse.adapters.mineru_api import parse_pdf, get_quota_summary
from src.parse.clean.cleaning import clean_mineru_markdown
from src.parse.ir.parsed_doc import ParsedDoc, DOC_TYPE_MAP
from src.parse.config.doc_types import infer_doc_type


# ============ 路径配置 ============

RAW_DIR = PROJECT_ROOT / "PDFs"
CLEANED_DIR = PROJECT_ROOT / "cleaned"
CLEANED_META_DIR = PROJECT_ROOT / "cleaned_meta"
CLEANED_DIR.mkdir(exist_ok=True)
CLEANED_META_DIR.mkdir(exist_ok=True)


# ============ 工具函数 ============

def compute_md5(filepath: str) -> str:
    """计算文件 MD5 哈希"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(filename: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符"""
    name = Path(filename).stem
    # 只保留字母数字中文 -_
    name = "".join(c for c in name if c.isalnum() or c in "-_ ")
    name = name.strip()[:max_len]
    return name


# ============ 单文件处理 ============

def process_single_pdf(pdf_path: str, skip_mineru: bool = False) -> Optional[str]:
    """
    处理单个 PDF:
      PDF → MinerU 解析 → 清洗 → 章节标记 → 保存 md + meta

    返回 doc_id 或 None(失败)
    """
    pdf_path = str(pdf_path)
    if not os.path.exists(pdf_path):
        print(f"❌ 文件不存在: {pdf_path}")
        return None

    file_name = os.path.basename(pdf_path)
    doc_id = Path(pdf_path).stem
    # 清理 doc_id
    doc_id = safe_filename(doc_id)

    cleaned_md_path = CLEANED_DIR / f"{doc_id}.md"
    cleaned_meta_path = CLEANED_META_DIR / f"{doc_id}.json"

    # ===== 1. MinerU 解析 =====
    if skip_mineru and cleaned_md_path.exists():
        print(f"⏭️  跳过 MinerU, 使用已有文件: {cleaned_md_path}")
        md_text = cleaned_md_path.read_text(encoding="utf-8")
    else:
        result = parse_pdf(pdf_path)
        if result is None:
            return None
        md_text = result["markdown"]
        content_list = result["content_list"]
        print(f"  MinerU 产出: {len(md_text)} 字符, content_list 含 {len(content_list)} 项")

    # ===== 2. 文档类型推断（文件名 → LLM 兜底） =====
    doc_type, doc_type_cn = infer_doc_type(file_name, pdf_path)
    print(f"  🏷️  文档类型: {doc_type} ({doc_type_cn})")
    extra_info = {}

    # ===== 3. 清洗 + 章节标记（按类型加载章节映射） =====
    cleaned_md, normalized_values = clean_mineru_markdown(md_text, doc_type)
    cleaned_md_path.write_text(cleaned_md, encoding="utf-8")
    print(f"  ✅ 清洗后 Markdown 保存: {cleaned_md_path}")

    # ===== 4. 构建 ParsedDoc 元数据 =====
    md5 = compute_md5(pdf_path)
    meta = ParsedDoc(
        doc_id=doc_id,
        doc_type=doc_type,
        doc_type_cn=doc_type_cn,
        title=file_name,
        source_loc=pdf_path,
        markdown_path=str(cleaned_md_path),
        normalized_values=normalized_values,
        extra_info=extra_info,
    )
    cleaned_meta_path.write_text(
        meta.model_dump_json(ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  ✅ 元数据保存: {cleaned_meta_path}")

    return doc_id


# ============ 批处理 ============

def process_directory(dir_path: str, max_files: int = 5):
    """批量处理目录中的 PDF 文件"""
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        print(f"❌ 目录不存在: {dir_path}")
        return

    pdfs = sorted(
        p for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() == ".pdf"
    )
    if not pdfs:
        print(f"❌ 目录中无 PDF 文件: {dir_path}")
        return

    print(f"📂 找到 {len(pdfs)} 个 PDF 文件")
    print(get_quota_summary())
    print()

    # 先检查配额总量
    total_pages = 0
    from src.parse.adapters.mineru_api import get_pdf_page_count
    for pdf in pdfs:
        total_pages += get_pdf_page_count(str(pdf))
    print(f"📊 总计 {len(pdfs)} 个文件, {total_pages} 页")
    print()

    processed = 0
    failures = 0
    for pdf in pdfs[:max_files]:
        print(f"\n{'='*60}")
        doc_id = process_single_pdf(str(pdf))
        if doc_id:
            processed += 1
        else:
            failures += 1
        # 避免请求过快
        time.sleep(1)

    print(f"\n{'='*60}")
    print(f"✅ 完成: {processed} 成功, {failures} 失败")
    print(get_quota_summary())


# ============ LlamaIndex 索引构建 ============

def build_vector_index():
    """用 LlamaIndex 构建向量索引(PGVectorStore)"""
    from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings
    from llama_index.core.node_parser import MarkdownNodeParser
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    # 使用本地 BGE 嵌入模型(免费)
    print("📦 加载 BGE 嵌入模型...")
    Settings.embed_model = HuggingFaceEmbedding(
        model_name="BAAI/bge-small-zh-v1.5",
        embed_batch_size=32,
        device="cpu",
    )

    # 读取清洗后的 markdown
    md_files = list(CLEANED_DIR.glob("*.md"))
    if not md_files:
        print(f"❌ cleaned/ 目录无 markdown 文件, 请先运行 pipeline.py run")
        return

    print(f"📂 加载 {len(md_files)} 个 markdown 文件...")
    documents = SimpleDirectoryReader(
        input_dir=str(CLEANED_DIR),
        file_metadata=lambda f: {"file_name": os.path.basename(f)},
    ).load_data()

    print(f"📄 共 {len(documents)} 个文档")
    print(f"🔧 用 MarkdownNodeParser 按章节切片...")

    # 构建向量索引(内存模式, 暂不依赖 PG)
    index = VectorStoreIndex.from_documents(
        documents,
        transformations=[MarkdownNodeParser()],
        show_progress=True,
    )

    print(f"✅ 向量索引构建完成! 共 {len(index.ref_doc_info)} 个文档")
    print(f"\n💡 检索测试: 输入问题查询(输入 q 退出)")

    # 交互式检索
    query_engine = index.as_query_engine(similarity_top_k=5)
    while True:
        query = input("\n🔍 查询: ").strip()
        if query.lower() in ("q", "quit", "exit"):
            break
        response = query_engine.query(query)
        print(f"\n📝 回答: {response}")
        print(f"\n📎 来源:")
        for i, node in enumerate(response.source_nodes):
            print(f"  [{i+1}] {node.node.get_metadata().get('file_name', '?')}")
            print(f"      {node.node.get_content()[:100]}...")


# ============ CLI ============

def main():
    parser = argparse.ArgumentParser(description="B 阶段解析清洗流水线")
    sub = parser.add_subparsers(dest="command")

    # run 子命令
    run_p = sub.add_parser("run", help="运行 PDF 解析流水线")
    run_p.add_argument("--pdf", help="单个 PDF 文件路径")
    run_p.add_argument("--dir", help="PDF 目录")
    run_p.add_argument("--max", type=int, default=5, help="最大处理文件数(默认 5)")
    run_p.add_argument("--skip-mineru", action="store_true", help="跳过 MinerU, 使用已有 cleaned md")

    # index 子命令
    sub.add_parser("index", help="构建 LlamaIndex 向量索引")

    # quota 子命令
    quota_p = sub.add_parser("quota", help="查看 MinerU 配额")

    args = parser.parse_args()

    if args.command == "run":
        if args.pdf:
            process_single_pdf(args.pdf)
        elif args.dir:
            process_directory(args.dir, args.max)
        else:
            # 默认处理 PDFs/ 目录
            process_directory(str(RAW_DIR), 3)
    elif args.command == "index":
        build_vector_index()
    elif args.command == "quota":
        print(get_quota_summary())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()