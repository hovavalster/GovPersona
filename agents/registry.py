"""
Agent registry — loads from config/agents.json.
New agents are added by editing that file or using add_agent().
"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, List, Tuple

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "agents.json"
)
_KB_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "knowledge_base"
)

_BUILTIN_AGENTS: Dict[str, Any] = {
    "finance_ministry": {
        "name": "Ministry of Finance (משרד האוצר)",
        "name_he": "משרד האוצר",
        "name_en": "Ministry of Finance",
        "role_title": "Senior Economist / Budget Division Director",
        "org_mandate": (
            "Responsible for Israel's state budget, tax policy, fiscal policy, "
            "and economic planning. Oversees public spending, revenue collection, "
            "and macroeconomic stability."
        ),
        "tone": "formal, data-driven, fiscally conservative",
        "collection_id": "finance_ministry",
        "knowledge_base_dir": "finance_ministry",
    },
    "central_bank": {
        "name": "Bank of Israel (בנק ישראל)",
        "name_he": "בנק ישראל",
        "name_en": "Bank of Israel",
        "role_title": "Senior Monetary Economist / Research Department Director",
        "org_mandate": (
            "Israel's central bank. Responsible for monetary policy, maintaining "
            "price stability, financial system stability, regulating banks and payment "
            "systems, and managing foreign currency reserves."
        ),
        "tone": "formal, analytical, monetary-policy focused, data-driven",
        "collection_id": "central_bank",
        "knowledge_base_dir": "central_bank",
    },
    "securities_authority": {
        "name": "Israel Securities Authority (רשות ניירות ערך)",
        "name_he": "רשות ניירות ערך",
        "name_en": "Israel Securities Authority",
        "role_title": "Senior Legal Counsel / Supervision Division Director",
        "org_mandate": (
            "Regulates and supervises the capital markets in Israel. Protects investors, "
            "ensures fair and efficient markets, enforces securities laws, and oversees "
            "public companies, mutual funds, and investment advisors."
        ),
        "tone": "formal, legal-regulatory, investor-protection focused",
        "collection_id": "securities_authority",
        "knowledge_base_dir": "securities_authority",
    },
}


def _load_registry() -> Dict[str, Any]:
    """Load agents.json, writing built-ins if file is missing."""
    if not os.path.exists(_CONFIG_PATH):
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        _write_registry(_BUILTIN_AGENTS)
        return dict(_BUILTIN_AGENTS)
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_registry(data: Dict[str, Any]):
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_agent(org_id: str) -> Dict[str, Any]:
    """Return config dict for a single agent. Raises KeyError if not found."""
    registry = _load_registry()
    if org_id not in registry:
        raise KeyError(f"Agent '{org_id}' not found in registry.")
    return registry[org_id]


def list_agents() -> List[Tuple[str, str]]:
    """Return [(org_id, display_name), ...] sorted by display_name."""
    registry = _load_registry()
    return sorted(
        [(oid, cfg["name"]) for oid, cfg in registry.items()],
        key=lambda x: x[1],
    )


def add_agent(org_id: str, config_dict: Dict[str, Any]) -> bool:
    """
    Add a new agent to the registry.
    Creates knowledge_base/<org_id>/ folder.
    Returns True on success, False if org_id already exists.
    """
    org_id = org_id.strip().lower().replace(" ", "_")
    registry = _load_registry()
    if org_id in registry:
        return False

    config_dict["collection_id"] = org_id
    config_dict["knowledge_base_dir"] = org_id
    registry[org_id] = config_dict

    # Create KB directory
    kb_dir = os.path.join(_KB_ROOT, org_id)
    os.makedirs(kb_dir, exist_ok=True)

    _write_registry(registry)
    return True


def delete_agent(org_id: str) -> bool:
    """
    Remove agent from registry (does NOT delete ChromaDB collection or files).
    Returns True if deleted, False if not found.
    """
    registry = _load_registry()
    if org_id not in registry:
        return False
    del registry[org_id]
    _write_registry(registry)
    return True
