"""Fetch the public source and prepare selected columns without filtering observations."""

import argparse
import httpx
from sqlalchemy import select
from ..config import Settings
from ..errors import AppError
from ..datasets import files, service
from ..datasets.models import Dataset, FieldPatch

DOI = "10.17632/rrfwny7byp.1"
SOURCE_URL = "https://data.mendeley.com/datasets/rrfwny7byp/1"
FILE_URL = "https://data.mendeley.com/public-files/datasets/rrfwny7byp/files/0fcbe6dc-7a0d-49f0-8664-dde2ab80ecb6/file_downloaded"
EXPECTED_SIZE = 332_614_843
COLUMNS = {
    "Symbol": "firm_id",
    "year": "year",
    "IndustryCode": "industry_code",
    "PROVINCECODE": "province_code",
    "CITYCODE": "city_code",
    "carbon_post": "industry_peer_exposure",
    "green_patent1": "green_all_independent",
    "green_patent2": "green_invention_independent",
    "green_patent3": "green_utility_independent",
    "green_patent4": "green_all_joint",
    "green_patent5": "green_invention_joint",
    "green_patent6": "green_utility_joint",
    "Size": "total_assets",
    "Lev": "leverage",
    "ROA": "return_on_assets",
    "SOE": "state_ownership",
    "HHI_A": "industry_concentration",
    "FC_index": "fc_index",
    "KZ_index": "kz_index",
    "SA_index": "sa_index",
    "WW_index": "ww_index",
}
SOURCE = {
    "url": SOURCE_URL,
    "doi": DOI,
    "license": "CC BY 4.0",
    "citation": "Wei, Daihui (2025), “Industry Peer Effect of Corporate Green Innovation”, Mendeley Data, V1, doi:10.17632/rrfwny7byp.1. 原始数据仅选列、重命名，不做行筛选。",
}


def fetch(settings):
    directory = settings.storage_dir() / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "data.dta"
    if target.exists():
        if target.stat().st_size != EXPECTED_SIZE:
            raise AppError("source_size", "已有 data.dta 大小不符，保留原文件；请检查来源")
        print(f"原始数据已存在，大小核验通过：{EXPECTED_SIZE:,} 字节", flush=True)
        return target
    partial = directory / "data.dta.partial"
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > EXPECTED_SIZE:
        raise AppError("source_size", "下载片段超过预期大小，保留片段；请检查来源")
    files.check_storage(settings, EXPECTED_SIZE - offset)
    if offset < EXPECTED_SIZE:
        headers = {"User-Agent": "Mozilla/5.0 HypoWeaver/2.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with httpx.stream("GET", FILE_URL, headers=headers, follow_redirects=True, timeout=60) as response:
            response.raise_for_status()
            if offset and (
                response.status_code != 206
                or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")
            ):
                raise AppError("resume_unsupported", "来源未接受断点续传，现有下载片段保留，请检查后重试")
            with partial.open("ab") as stream:
                progress = offset // (32 * 1024**2)
                for chunk in response.iter_bytes(1024**2):
                    if offset + len(chunk) > EXPECTED_SIZE:
                        raise AppError("source_size", "远端文件超过预期大小，已停止下载")
                    stream.write(chunk)
                    offset += len(chunk)
                    if offset // (32 * 1024**2) > progress:
                        progress = offset // (32 * 1024**2)
                        print(f"已下载 {offset / 1024**2:.0f} / {EXPECTED_SIZE / 1024**2:.0f} MB", flush=True)
    if partial.stat().st_size != EXPECTED_SIZE:
        raise AppError("source_size", "下载未完成，下次 fetch 可尝试断点续传")
    partial.rename(target)
    print(f"下载完成，大小核验通过：{EXPECTED_SIZE:,} 字节", flush=True)
    return target


def prepare(settings, project_id=None):
    from ..app import create_app
    from ..db import Base

    app = create_app(settings)
    sessions = app.state.sessions
    Base.metadata.create_all(sessions.kw["bind"])
    from ..migrations import migrate

    migrate(sessions.kw["bind"])
    path = settings.storage_dir() / "raw" / "data.dta"
    if not path.exists() or path.stat().st_size != EXPECTED_SIZE:
        raise AppError("source_missing", "请先运行 carbon fetch，核验原始文件大小")
    meta = files.inspect(path)
    available = {c["name"] for c in meta["columns"]}
    missing = set(COLUMNS) - available
    if missing:
        raise AppError("source_columns", "来源缺少预期字段：" + ", ".join(sorted(missing)))
    frame = files.read_selected(path, list(COLUMNS)).rename(columns=COLUMNS)
    labels = {COLUMNS[c["name"]]: c["label"] for c in meta["columns"] if c["name"] in COLUMNS}
    with sessions() as db:
        if project_id:
            from ..projects.service import get

            get(db, project_id)
        existing = db.scalars(select(Dataset).where(Dataset.name == "碳市场企业面板 · Mendeley V1")).all()
        for item in existing:
            if item.source.get("doi") == DOI and item.selected_columns == list(COLUMNS.values()):
                service.update_field(
                    db, item.id, "industry_peer_exposure", FieldPatch(semantics="peer_exposure", level="industry")
                )
                print(f"数据资产已登记：{item.id}，{item.n_rows:,} 行", flush=True)
                return item.id
        item = service.register(
            settings,
            db,
            frame,
            "碳市场企业面板 · Mendeley V1",
            SOURCE,
            "dta",
            labels=labels,
            project_id=project_id,
            unit="firm_id",
            time="year",
        )
        service.update_field(
            db, item.id, "industry_peer_exposure", FieldPatch(semantics="peer_exposure", level="industry")
        )
        print(f"已登记 {item.id}：{item.n_rows:,} 行，{item.n_cols} 列；面板 {item.panel}", flush=True)
        return item.id


def main():
    parser = argparse.ArgumentParser(description="公开碳市场数据获取与准备")
    parser.add_argument("command", choices=["fetch", "prepare"])
    parser.add_argument("--project-id")
    args = parser.parse_args()
    try:
        settings = Settings()
        fetch(settings) if args.command == "fetch" else prepare(settings, args.project_id)
    except (AppError, httpx.HTTPError) as exc:
        parser.exit(1, (exc.message if isinstance(exc, AppError) else str(exc)) + "\n")


if __name__ == "__main__":
    main()
