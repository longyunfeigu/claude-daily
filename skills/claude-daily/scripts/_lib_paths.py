# input: outbox_dir + date + member_id from config
# output: member_outbox(), archive_dir(), atomic_write_json(), atomic_write_text()
# owner: wanhua.gu
# pos: skill shared lib - paths; 一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Outbox path resolution + atomic write helpers."""
import json
import os
import tempfile
from pathlib import Path


def member_outbox(outbox_dir: str, date: str, member_id: str) -> Path:
    """Return ~/.local/state/compound-daily/outbox/<date>/<member_id>/ as Path; ensure parents exist."""
    p = Path(outbox_dir) / date / member_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def archive_dir(outbox_dir: str, date: str, member_id: str, ts: str) -> Path:
    """Return outbox/_archive/<ts>/<date>/<member_id>/."""
    return Path(outbox_dir) / "_archive" / ts / date / member_id


def atomic_write_json(path: Path, data) -> None:
    """Atomic write via tempfile + os.replace (POSIX rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent),
        prefix=path.name + ".", suffix=".tmp", delete=False,
    )
    try:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent),
        prefix=path.name + ".", suffix=".tmp", delete=False,
    )
    try:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
