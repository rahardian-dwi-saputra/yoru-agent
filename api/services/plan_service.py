import hashlib
import json
from datetime import datetime, timedelta, timezone
import random
from typing import Any, Dict, List, Optional

from api.config import PROJECT_ROOT

PLANS_DIR = PROJECT_ROOT / "storage" / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)


def generate_plan_id(prefix: str = "hp") -> str:
    """Membuat ID plan unik dengan format: {prefix}-short_hash-nomor_urut"""
    now_str = datetime.now(timezone.utc).isoformat()
    rand_val = str(random.randint(1000, 9999))
    short_hash = hashlib.md5(f"{now_str}_{rand_val}".encode()).hexdigest()[:6]
    nomor_urut = random.randint(10, 99)
    return f"{prefix}-{short_hash}-{nomor_urut}"


def create_action_plan(
    action: str, catalogs: List[str], catalog_single: Optional[str] = None
) -> Dict[str, Any]:
    """Membuat file JSON action plan (hardening/rollback) dan menyimpannya ke storage/plans/"""
    prefix = "rp" if action.lower() == "rollback" else "hp"
    plan_id = generate_plan_id(prefix=prefix)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    plan_data = {
        "plan_id": plan_id,
        "action": action.lower(),
        "status": "pending_approval",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "catalogs": catalogs,
    }

    if catalog_single:
        plan_data["catalog"] = catalog_single

    file_path = PLANS_DIR / f"{plan_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)

    return plan_data

def create_hardening_plan(
    catalogs: List[str], catalog_single: Optional[str] = None
) -> Dict[str, Any]:
    """Membuat file JSON hardening plan dan menyimpannya ke storage/plans/"""
    plan_id = generate_plan_id()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    plan_data = {
        "plan_id": plan_id,
        "status": "pending_approval",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "catalogs": catalogs,
    }

    if catalog_single:
        plan_data["catalog"] = catalog_single

    file_path = PLANS_DIR / f"{plan_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)

    return plan_data

def get_plan(plan_id: str) -> Optional[Dict[str, Any]]:
    """Membaca isi file plan dari disk"""
    file_path = PLANS_DIR / f"{plan_id}.json"
    if not file_path.is_file():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def update_and_expire_plan(plan_id: str, status: str) -> None:
    """Mengubah status plan dan membuat statusnya langsung expired"""
    plan_data = get_plan(plan_id)
    if not plan_data:
        return

    plan_data["status"] = status
    plan_data["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()

    file_path = PLANS_DIR / f"{plan_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)


def is_plan_valid(plan_data: Dict[str, Any]) -> bool:
    """Memeriksa apakah plan masih berlaku dan berstatus pending_approval"""
    if plan_data.get("status") != "pending_approval":
        return False

    expires_at_str = plan_data.get("expires_at")
    if not expires_at_str:
        return False

    expires_at = datetime.fromisoformat(expires_at_str)
    return datetime.now(timezone.utc) < expires_at