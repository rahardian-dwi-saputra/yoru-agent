import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(
    title="Yoru Agent - Hardening API",
    version="1.0.0",
    description="API Hardening berbasis Hermes Agent dengan mekanisme Human-in-the-Loop (HITL) Confirmation."
)

# ==========================================
# KONFIGURASI PATH MOUNTING
# ==========================================
# main.py ada di: yoru-agent/api/main.py
API_DIR = Path(__file__).resolve().parent
BASE_DIR = API_DIR.parent  # Mengarah ke: yoru-agent/

# Path scripts & logs untuk K01
SCRIPTS_DIR_K01 = BASE_DIR / "catalog" / "K01" / "scripts"
LOGS_DIR_K01 = BASE_DIR / "catalog" / "K01" / "logs"

# Path scripts & logs untuk K03
SCRIPTS_DIR_K03 = BASE_DIR / "catalog" / "K03" / "scripts"
LOGS_DIR_K03 = BASE_DIR / "catalog" / "K03" / "logs"

# Pastikan direktori logs dibuat jika belum ada
LOGS_DIR_K01.mkdir(parents=True, exist_ok=True)
LOGS_DIR_K03.mkdir(parents=True, exist_ok=True)


# ==========================================
# MODEL PYDANTIC
# ==========================================

# Model Input Request
class TriggerRequest(BaseModel):
    requested_intent: str = Field(
        ...,
        description="Instruksi user, misal: 'amankan root', 'batasi percobaan login', 'ya', 'tidak'.",
        examples=["amankan root", "batasi percobaan login", "Ya", "Tidak"],
    )
    pending_action: Optional[Literal["hardening", "rollback"]] = Field(
        default=None,
        description="Aksi tertunda yang menunggu konfirmasi user (dikirim kembali oleh client saat konfirmasi).",
    )

# Base Model Output Response
class BaseHardeningResponse(BaseModel):
    endpoint_id: str = Field(
        ...,
        description="ID Endpoint penangan modul (misal: 'K01' atau 'K03').",
    )
    status: Literal["completed", "pending_confirmation", "cancelled", "error"] = Field(
        ...,
        description="Status eksekusi workflow dari FastAPI.",
    )
    selected_action: Literal["audit", "hardening", "rollback", "none"] = Field(
        ...,
        description="Jenis aksi yang diidentifikasi oleh engine.",
    )
    requires_confirmation: bool = Field(
        ...,
        description="Penanda apakah langkah ini membutuhkan persetujuan user.",
    )
    confirmation_message: Optional[str] = Field(
        default=None,
        description="Pesan konfirmasi yang harus ditampilkan ke user jika status=pending_confirmation.",
    )
    execution_code: Optional[int] = Field(
        default=None,
        description="Exit code dari Taskfile / script hardening (0 = sukses).",
    )
    action_logs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Log rinci hasil audit atau eksekusi perintah terminal.",
    )


# Model Output Response khusus K01
class K01Response(BaseHardeningResponse):
    """Model Response Khusus Endpoint /K01 (SSH Root Access Rules)"""

    endpoint_id: Literal["K01"] = "K01"


# Model Output Response khusus K03
class K03Response(BaseHardeningResponse):
    """Model Response Khusus Endpoint /K03 (SSH Login Limits & Timeouts)"""

    endpoint_id: Literal["K03"] = "K03"


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def run_taskfile_action(action: str, scripts_dir: Path) -> int:
    """Execution Layer: Memanggil Taskfile menggunakan sudo secara asynchronous dari folder scripts yang ditentukan."""
    # Menambahkan 'sudo', '-E', 'task' agar dieksekusi dengan privilege root tanpa password
    process = await asyncio.create_subprocess_exec(
        "sudo", "-E", "task", action,
        cwd=str(scripts_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    # Cetak log jika ada error dari stderr untuk mempermudah debugging
    if process.returncode != 0:
        print(f"[ERROR] Taskfile execution failed with exit code {process.returncode}")
        print(f"[STDERR]: {stderr.decode('utf-8')}")

    return process.returncode


def read_action_logs(action: str, logs_dir: Path) -> List[Dict[str, Any]]:
    """Log Parser: Membaca log JSON spesifik action dari folder logs yang ditentukan."""
    log_file_path = logs_dir / f"{action}.json"
    if not log_file_path.exists():
        return []

    logs = []
    with open(log_file_path, mode="r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                try:
                    logs.append(json.loads(line_str))
                except json.JSONDecodeError:
                    continue
    return logs

async def process_hardening_intent(
    endpoint_id: str,
    payload: TriggerRequest,
    scripts_dir: Path,
    logs_dir: Path,
    hardening_keywords: List[str],
    hardening_warning_msg: str,
    rollback_warning_msg: str,
) -> Dict[str, Any]:
    """Core Workflow Handler: Generic logic untuk memproses HITL dan instruksi pada /K01 dan /K03."""
    intent_lower = payload.requested_intent.strip().lower()

    # -------------------------------------------------------------
    # TAHAP 1: Menangani Respon Konfirmasi (User Menjawab Ya / Tidak)
    # -------------------------------------------------------------
    if payload.pending_action in ["hardening", "rollback"]:
        action_to_execute = payload.pending_action

        # Jika User Setuju (Ya / Yes / Lanjutkan)
        if intent_lower in ["ya", "yes", "setuju", "lanjutkan", "y"]:
            exec_code = await run_taskfile_action(action_to_execute, scripts_dir)

            if exec_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Hermes Agent gagal mengeksekusi '{action_to_execute}' pada {endpoint_id}.",
                )

            return {
                "endpoint_id": endpoint_id,
                "status": "completed",
                "selected_action": action_to_execute,
                "requires_confirmation": False,
                "confirmation_message": f"Konfirmasi diterima. Tindakan {action_to_execute} berhasil dieksekusi pada {endpoint_id}.",
                "execution_code": exec_code,
                "action_logs": read_action_logs(action_to_execute, logs_dir),
            }

        # Jika User Membatalkan (Tidak / No / Batal)
        elif intent_lower in ["tidak", "no", "batal", "n"]:
            return {
                "endpoint_id": endpoint_id,
                "status": "cancelled",
                "selected_action": "none",
                "requires_confirmation": False,
                "confirmation_message": f"Tindakan {action_to_execute} pada {endpoint_id} telah dibatalkan oleh pengguna.",
                "execution_code": 0,
                "action_logs": [],
            }

        # Jika respon konfirmasi tidak jelas
        else:
            return {
                "endpoint_id": endpoint_id,
                "status": "pending_confirmation",
                "selected_action": action_to_execute,
                "requires_confirmation": True,
                "confirmation_message": f"Jawaban tidak dikenali. Mohon jawab 'Ya' untuk melanjutkan {action_to_execute} pada {endpoint_id} atau 'Tidak' untuk membatalkan.",
                "execution_code": None,
                "action_logs": [],
            }

    # -------------------------------------------------------------
    # TAHAP 2: Evaluasi Intent Awal oleh Hermes Agent
    # -------------------------------------------------------------

    # 1. Deteksi Hardening -> Butuh Konfirmasi
    if any(k in intent_lower for k in hardening_keywords):
        return {
            "endpoint_id": endpoint_id,
            "status": "pending_confirmation",
            "selected_action": "hardening",
            "requires_confirmation": True,
            "confirmation_message": hardening_warning_msg,
            "execution_code": None,
            "action_logs": [],
        }

    # 2. Deteksi Rollback -> Butuh Konfirmasi
    elif any(k in intent_lower for k in ["rollback", "kembalikan", "restore", "undo"]):
        return {
            "endpoint_id": endpoint_id,
            "status": "pending_confirmation",
            "selected_action": "rollback",
            "requires_confirmation": True,
            "confirmation_message": rollback_warning_msg,
            "execution_code": None,
            "action_logs": [],
        }

    # 3. Audit / Default -> Aman untuk Langsung Dieksekusi (Rendah Risiko)
    else:
        exec_code = await run_taskfile_action("audit", scripts_dir)
        return {
            "endpoint_id": endpoint_id,
            "status": "completed",
            "selected_action": "audit",
            "requires_confirmation": False,
            "confirmation_message": f"Tindakan audit pada {endpoint_id} aman dijalankan tanpa konfirmasi.",
            "execution_code": exec_code,
            "action_logs": read_action_logs("audit", logs_dir),
        }


# ==========================================
# ENDPOINT K01
# ==========================================

@app.post(
    "/K01",
    response_model=K01Response,
    status_code=status.HTTP_200_OK,
    summary="Interactive SSH Root Security Action Trigger with HITL (CIS 5.1.x)",
)
async def trigger_k01(payload: TriggerRequest):
    result = await process_hardening_intent(
        endpoint_id="K01",
        payload=payload,
        scripts_dir=SCRIPTS_DIR_K01,
        logs_dir=LOGS_DIR_K01,
        hardening_keywords=["hardening", "amankan", "matikan root", "secure", "root"],
        hardening_warning_msg="PERHATIAN: Hardening K01 akan mematikan SSH Root Login. Apakah Anda yakin ingin melanjutkan? (Jawab 'Ya' atau 'Tidak')",
        rollback_warning_msg="PERHATIAN: Rollback K01 akan mengembalikan konfigurasi SSH Root Login ke kondisi awal. Apakah Anda yakin? (Jawab 'Ya' atau 'Tidak')",
    )
    return K01Response(**result)


# ==========================================
# ENDPOINT K03
# ==========================================

@app.post(
    "/K03",
    response_model=K03Response,
    status_code=status.HTTP_200_OK,
    summary="Interactive SSH Login Limits Action Trigger with HITL (CIS 5.1.13 & 5.1.16)",
)
async def trigger_k03(payload: TriggerRequest):
    result = await process_hardening_intent(
        endpoint_id="K03",
        payload=payload,
        scripts_dir=SCRIPTS_DIR_K03,
        logs_dir=LOGS_DIR_K03,
        hardening_keywords=["hardening", "amankan", "batasi login", "limit login", "maxauth", "grace time"],
        hardening_warning_msg="PERHATIAN: Hardening K03 akan membatasi percobaaan login SSH (MaxAuthTries & LoginGraceTime). Apakah Anda yakin ingin melanjutkan? (Jawab 'Ya' atau 'Tidak')",
        rollback_warning_msg="PERHATIAN: Rollback K03 akan mengembalikan batasan login SSH ke nilai default. Apakah Anda yakin? (Jawab 'Ya' atau 'Tidak')",
    )
    return K03Response(**result)