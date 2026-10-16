"""旧仓库导入的真实案例（只读展示）。project.case 以 legacy: 开头。"""

PREFIX = "legacy:"


def is_legacy(project) -> bool:
    return bool(project and (project.case or "").startswith(PREFIX))
