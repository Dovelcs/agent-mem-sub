from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._+-]*", re.I)


ALIASES: list[tuple[set[str], tuple[str, ...], str]] = [
    (
        {"flash", "flashing", "upgrade", "update.img", "fastboot", "ota", "maskrom", "loader"},
        ("烧录", "升级", "刷机"),
        " decision_policy route_guard verified_route pitfall fastboot upgrade_tool rkdeveloptool OTA update.img partition Loader Maskrom adb usb transport route selection 烧录 升级 镜像 路线选择 优先级",
    ),
    (
        {"ssh", "credential", "ip", "tailscale"},
        ("连接", "登录", "服务器", "设备", "密码", "账号", "凭据"),
        " credential_location agent_route pitfall ssh alias wrapper mcp tailscale ip user password secret 凭据 账号 密码 连接 设备",
    ),
    (
        {"mcp", "hook", "agent-memory", "memory", "qdrant", "embedding"},
        ("记忆", "召回"),
        " agent-memory recall route_guard pitfall workflow_policy memory-taxonomy UserPromptSubmit Qdrant embedding FTS MCP skill 记忆分类 召回路线",
    ),
    (
        {"pdf", "docx", "datasheet", "guide", "manifest", "summary"},
        ("文档", "资料", "手册", "索引", "来源"),
        " doc_index official_doc source manifest summary provenance dedupe docs index 文档索引 来源清单 去重 官方文档",
    ),
    (
        {
            "dts",
            "dtsi",
            "pinctrl",
            "gpio",
            "i2c",
            "spi",
            "can",
            "uart",
            "usb",
            "kernel",
            "mipi",
            "dsi",
            "csi",
            "edp",
            "hdmi",
            "drm",
            "display",
            "camera",
            "vop",
            "lvds",
        },
        ("device tree", "外设", "驱动"),
        " hardware_debug project_fact route_guard verified_route DTS dtsi pinctrl driver kernel runtime probe docs reference code 外设 调试",
    ),
    (
        {"git", "commit", "merge", "rebase", "jira", "review", "docx", "xlsx"},
        ("文档交付", "客户"),
        " workflow_policy verified_route pitfall commit review jira customer deliverable sync 文档交付 客户 流程",
    ),
]


def text_tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


def rule_matches(text: str, tokens: set[str], token_terms: set[str], phrase_terms: tuple[str, ...]) -> bool:
    if tokens & token_terms:
        return True
    lowered = text.lower()
    return any(term.lower() in lowered for term in phrase_terms)


def expand_prompt(payload: dict[str, Any]) -> str:
    prompt = str(payload.get("prompt") or "")
    context = " ".join(
        str(payload.get(key) or "") for key in ("cwd", "repo", "branch", "platform", "tool")
    )
    text = " ".join(part for part in (prompt, context) if part).strip()
    tokens = text_tokens(text)
    additions: list[str] = []
    for token_terms, phrase_terms, alias in ALIASES:
        if rule_matches(text, tokens, token_terms, phrase_terms):
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
