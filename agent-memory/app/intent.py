from __future__ import annotations

import re
from typing import Any


ALIASES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(烧录|升级|刷机|flash|flashing|upgrade|update\.img|fastboot|ota|maskrom|loader)", re.I),
        " decision_policy route_guard verified_route pitfall fastboot upgrade_tool rkdeveloptool OTA update.img partition Loader Maskrom adb usb transport route selection 烧录 升级 镜像 路线选择 优先级",
    ),
    (
        re.compile(r"(连接|登录|ssh|server|服务器|设备|密码|账号|凭据|credential|ip|tailscale)", re.I),
        " credential_location agent_route pitfall ssh alias wrapper mcp tailscale ip user password secret 凭据 账号 密码 连接 设备",
    ),
    (
        re.compile(r"(mcp|hook|codex|agent|记忆|召回|memory|qdrant|embedding)", re.I),
        " agent-memory recall route_guard pitfall workflow_policy memory-taxonomy UserPromptSubmit Qdrant embedding FTS MCP skill 记忆分类 召回路线",
    ),
    (
        re.compile(r"(文档|资料|pdf|docx|datasheet|guide|手册|索引|来源|manifest|summary)", re.I),
        " doc_index official_doc source manifest summary provenance dedupe docs index 文档索引 来源清单 去重 官方文档",
    ),
    (
        re.compile(r"(dts|dtsi|pinctrl|gpio|i2c|spi|can|uart|usb|外设|驱动|kernel|device tree)", re.I),
        " hardware_debug project_fact route_guard verified_route DTS dtsi pinctrl driver kernel runtime probe docs reference code 外设 调试",
    ),
    (
        re.compile(r"(git|commit|merge|rebase|jira|review|文档交付|客户|docx|xlsx)", re.I),
        " workflow_policy verified_route pitfall commit review jira customer deliverable sync 文档交付 客户 流程",
    ),
]


def expand_prompt(payload: dict[str, Any]) -> str:
    prompt = str(payload.get("prompt") or "")
    context = " ".join(
        str(payload.get(key) or "") for key in ("cwd", "repo", "branch", "platform", "tool")
    )
    text = " ".join(part for part in (prompt, context) if part).strip()
    additions: list[str] = []
    for pattern, alias in ALIASES:
        if pattern.search(text):
            additions.append(alias)
    expanded = " ".join([prompt, *additions, context]).strip()
    return re.sub(r"\s+", " ", expanded)


def expansion_trace(original: str, expanded: str) -> dict[str, Any]:
    original_terms = set((original or "").split())
    expanded_terms = [term for term in (expanded or "").split() if term not in original_terms]
    return {
        "expanded": bool(expanded_terms),
        "added_terms_sample": expanded_terms[:24],
        "expanded_length": len(expanded),
    }
