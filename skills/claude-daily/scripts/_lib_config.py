# input: ~/.compound-daily/config.json, env vars COMPOUND_DAILY_*
# output: load(), validate(), default_config_path()
# owner: wanhua.gu
# pos: skill shared lib - config; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Config loader and validator for compound-daily skill.

Lookup order (highest first): CLI arg > env var > config.json > built-in default.
"""
import json
import os
import re
from pathlib import Path

_MEMBER_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{2,40}$")
_MEMBER_ID_SEPARATOR_RE = re.compile(r"[._-]")
_ENV_PREFIX = "COMPOUND_DAILY_"
_ENV_KEYS = {
    "member_id":     "MEMBER_ID",
    "endpoint_base": "ENDPOINT_BASE",
    "outbox_dir":    "OUTBOX_DIR",
    "projects_root": "PROJECTS_ROOT",
}
_DEFAULTS = {
    "outbox_dir":    "~/.local/state/compound-daily/outbox",
    "projects_root": "~/.claude/projects",
}


def default_config_path() -> Path:
    return Path(os.path.expanduser("~/.compound-daily/config.json"))


def load(path: Path = None) -> dict:
    """Load + validate config. Returns dict with paths expanded."""
    path = path or default_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"config not found: {path}\n"
            f"  copy config.example.json (in the skill dir) to {path} and edit"
        )
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Apply built-in defaults
    for key, val in _DEFAULTS.items():
        cfg.setdefault(key, val)

    # Apply env overrides
    for key, env_suffix in _ENV_KEYS.items():
        env_val = os.environ.get(_ENV_PREFIX + env_suffix)
        if env_val:
            cfg[key] = env_val

    # Expand ~ in paths
    for key in ("outbox_dir", "projects_root"):
        if key in cfg:
            cfg[key] = os.path.expanduser(cfg[key])

    # Validate
    errors = validate(cfg)
    if errors:
        raise ValueError("config validation failed:\n  " + "\n  ".join(errors))
    return cfg


def validate(cfg: dict) -> list:
    """Return list of error strings; empty if valid."""
    errors = []
    mid = cfg.get("member_id", "")
    if (not isinstance(mid, str)
            or not _MEMBER_ID_RE.match(mid)
            or not _MEMBER_ID_SEPARATOR_RE.search(mid)):
        errors.append(
            f"member_id {mid!r} must match ^[a-z][a-z0-9._-]{{2,40}}$ and contain a separator (. _ -)"
        )
    base = cfg.get("endpoint_base", "")
    if not isinstance(base, str) or not (base.startswith("http://") or base.startswith("https://")):
        errors.append(f"endpoint_base {base!r} must start with http:// or https://")
    paths = cfg.get("endpoint_paths") or {}
    if not paths.get("daily_report"):
        errors.append("endpoint_paths.daily_report is required")
    if not paths.get("session_card"):
        errors.append("endpoint_paths.session_card is required")
    return errors
