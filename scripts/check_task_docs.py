"""Validate documentation gates for completed Project Kei task files."""

from __future__ import print_function

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "tasks"
GATED_STATUSES = {"待集成", "已完成"}
REQUIRED_KEYS = (
    "TASK_RECORD",
    "TASKS_BOARD",
    "PUBLIC_README",
    "MODULE_CATALOG",
    "ARCHITECTURE_DOCS",
    "LOCAL_README",
    "AGENT_RULES",
    "VALIDATION",
)


def task_status(text):
    match = re.search(r"^- 状态：\s*(\S+)\s*$", text, flags=re.MULTILINE)
    return match.group(1) if match else ""


def gate_section(text):
    match = re.search(
        r"^## 完成文档门禁\s*$([\s\S]*?)(?=^##\s|\Z)",
        text,
        flags=re.MULTILINE,
    )
    return match.group(1) if match else ""


def main():
    errors = []
    checked = 0
    for path in sorted(TASKS_DIR.glob("PK-*.md")):
        text = path.read_text(encoding="utf-8")
        status = task_status(text)
        if status not in GATED_STATUSES:
            continue
        checked += 1
        section = gate_section(text)
        if not section:
            errors.append("{}: 缺少 ## 完成文档门禁".format(path.name))
            continue
        for key in REQUIRED_KEYS:
            pattern = r"^- \[[xX]\] {}\b".format(re.escape(key))
            if not re.search(pattern, section, flags=re.MULTILINE):
                errors.append("{}: 未勾选 {}".format(path.name, key))

    if errors:
        print("task documentation gate failed:")
        for error in errors:
            print("- " + error)
        return 1
    print("task documentation gate passed: {} gated task(s)".format(checked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
