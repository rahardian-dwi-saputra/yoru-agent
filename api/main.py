import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(
    title="Hermes Agent - HITL SSH Management API",
    version="2.0.0",
    description="API SSH Management berbasis Hermes Agent dengan mekanisme Human-in-the-Loop (HITL) Confirmation."
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
        description="Instruksi user, misal: 'amankan ssh', 'cek sistem', 'ya', 'tidak'."
    )
    pending_action: Optional[Literal["hardening", "rollback"]] = Field(
        default=None,
        description="Aksi tertunda yang menunggu konfirmasi user (dikirim kembali oleh client saat konfirmasi)."
    )


# Model Output Response untuk K01
class K01Response(BaseModel):
    status: Literal["completed", "pending_confirmation", "cancelled", "error"]
    selected_action: Literal["audit", "hardening", "rollback", "none"]
    requires_confirmation: bool
    confirmation_message: Optional[str] = None
    execution_code: Optional[int] = None
    action_logs: List[Dict[str, Any]] = []


# Model Output Response untuk K03
class K03Response(BaseModel):
    status: Literal["completed", "pending_confirmation", "cancelled", "error"]
    selected_action: Literal["audit", "hardening", "rollback", "none"]
    requires_confirmation: bool
    confirmation_message: Optional[str] = None
    execution_code: Optional[int] = None
    action_logs: List[Dict[str, Any]] = []


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


# ==========================================
# ENDPOINT K01
# ==========================================

@app.post(
    "/K01",
    response_model=K01Response,
    status_code=status.HTTP_200_OK,
    summary="Interactive SSH Security Action Trigger with HITL",
)
async def trigger_k01(payload: TriggerRequest):
    intent_lower = payload.requested_intent.strip().lower()

    # -------------------------------------------------------------
    # TAHAP 1: Menangani Respon Konfirmasi (User Menjawab Ya / Tidak)
    # -------------------------------------------------------------
    if payload.pending_action in ["hardening", "rollback"]:
        action_to_execute = payload.pending_action

        # Jika User Setuju (Ya / Yes / Lanjutkan)
        if intent_lower in ["ya", "yes", "setuju", "lanjutkan", "y"]:
            exec_code = await run_taskfile_action(action_to_execute, SCRIPTS_DIR_K01)
            
            if exec_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Hermes Agent gagal mengeksekusi '{action_to_execute}' pada K01."
                )

            return K01Response(
                status="completed",
                selected_action=action_to_execute,
                requires_confirmation=False,
                confirmation_message=f"Konfirmasi diterima. Tindakan {action_to_execute} berhasil dieksekusi.",
                execution_code=exec_code,
                action_logs=read_action_logs(action_to_execute, LOGS_DIR_K01)
            )

        # Jika User Membatalkan (Tidak / No / Batal)
        elif intent_lower in ["tidak", "no", "batal", "n"]:
            return K01Response(
                status="cancelled",
                selected_action="none",
                requires_confirmation=False,
                confirmation_message=f"Tindakan {action_to_execute} telah dibatalkan oleh pengguna.",
                execution_code=0,
                action_logs=[]
            )
        
        # Jika respon konfirmasi tidak jelas
        else:
            return K01Response(
                status="pending_confirmation",
                selected_action=action_to_execute,
                requires_confirmation=True,
                confirmation_message=f"Jawaban tidak dikenali. Mohon jawab 'Ya' untuk melanjutkan {action_to_execute} atau 'Tidak' untuk membatalkan."
            )

    # -------------------------------------------------------------
    # TAHAP 2: Evaluasi Intent Awal oleh Hermes Agent
    # -------------------------------------------------------------
    
    # 1. Deteksi Hardening -> Butuh Konfirmasi
    if any(k in intent_lower for k in ["hardening", "amankan", "matikan root", "secure"]):
        return K01Response(
            status="pending_confirmation",
            selected_action="hardening",
            requires_confirmation=True,
            confirmation_message="PERHATIAN: Hardening akan mematikan SSH Root Login. Apakah Anda yakin ingin melanjutkan? (Jawab 'Ya' atau 'Tidak')"
        )

    # 2. Deteksi Rollback -> Butuh Konfirmasi
    elif any(k in intent_lower for k in ["rollback", "kembalikan", "restore", "undo"]):
        return K01Response(
            status="pending_confirmation",
            selected_action="rollback",
            requires_confirmation=True,
            confirmation_message="PERHATIAN: Rollback akan mengembalikan konfigurasi SSH ke kondisi awal. Apakah Anda yakin? (Jawab 'Ya' atau 'Tidak')"
        )

    # 3. Audit / Auto -> Aman untuk Langsung Dieksekusi (Rendah Risiko)
    else:
        exec_code = await run_taskfile_action("audit", SCRIPTS_DIR_K01)
        return K01Response(
            status="completed",
            selected_action="audit",
            requires_confirmation=False,
            confirmation_message="Tindakan audit aman dijalankan tanpa konfirmasi.",
            execution_code=exec_code,
            action_logs=read_action_logs("audit", LOGS_DIR_K01)
        )


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
    intent_lower = payload.requested_intent.strip().lower()

    # -------------------------------------------------------------
    # TAHAP 1: Menangani Respon Konfirmasi (User Menjawab Ya / Tidak)
    # -------------------------------------------------------------
    if payload.pending_action in ["hardening", "rollback"]:
        action_to_execute = payload.pending_action

        # Jika User Setuju (Ya / Yes / Lanjutkan)
        if intent_lower in ["ya", "yes", "setuju", "lanjutkan", "y"]:
            exec_code = await run_taskfile_action(action_to_execute, SCRIPTS_DIR_K03)
            
            if exec_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Hermes Agent gagal mengeksekusi '{action_to_execute}' pada K03."
                )

            return K03Response(
                status="completed",
                selected_action=action_to_execute,
                requires_confirmation=False,
                confirmation_message=f"Konfirmasi diterima. Tindakan {action_to_execute} berhasil dieksekusi.",
                execution_code=exec_code,
                action_logs=read_action_logs(action_to_execute, LOGS_DIR_K03)
            )

        # Jika User Membatalkan (Tidak / No / Batal)
        elif intent_lower in ["tidak", "no", "batal", "n"]:
            return K03Response(
                status="cancelled",
                selected_action="none",
                requires_confirmation=False,
                confirmation_message=f"Tindakan {action_to_execute} telah dibatalkan oleh pengguna.",
                execution_code=0,
                action_logs=[]
            )
        
        # Jika respon konfirmasi tidak jelas
        else:
            return K03Response(
                status="pending_confirmation",
                selected_action=action_to_execute,
                requires_confirmation=True,
                confirmation_message=f"Jawaban tidak dikenali. Mohon jawab 'Ya' untuk melanjutkan {action_to_execute} atau 'Tidak' untuk membatalkan."
            )

    # -------------------------------------------------------------
    # TAHAP 2: Evaluasi Intent Awal oleh Hermes Agent
    # -------------------------------------------------------------
    
    # 1. Deteksi Hardening -> Butuh Konfirmasi
    if any(k in intent_lower for k in ["hardening", "amankan", "batasi login", "limit login", "maxauth"]):
        return K03Response(
            status="pending_confirmation",
            selected_action="hardening",
            requires_confirmation=True,
            confirmation_message="PERHATIAN: Hardening K03 akan membatasi percobaaan login SSH (MaxAuthTries & LoginGraceTime). Apakah Anda yakin ingin melanjutkan? (Jawab 'Ya' atau 'Tidak')"
        )

    # 2. Deteksi Rollback -> Butuh Konfirmasi
    elif any(k in intent_lower for k in ["rollback", "kembalikan", "restore", "undo"]):
        return K03Response(
            status="pending_confirmation",
            selected_action="rollback",
            requires_confirmation=True,
            confirmation_message="PERHATIAN: Rollback K03 akan mengembalikan batasan login SSH ke nilai default. Apakah Anda yakin? (Jawab 'Ya' atau 'Tidak')"
        )

    # 3. Audit / Auto -> Aman untuk Langsung Dieksekusi (Rendah Risiko)
    else:
        exec_code = await run_taskfile_action("audit", SCRIPTS_DIR_K03)
        return K03Response(
            status="completed",
            selected_action="audit",
            requires_confirmation=False,
            confirmation_message="Tindakan audit K03 aman dijalankan tanpa konfirmasi.",
            execution_code=exec_code,
            action_logs=read_action_logs("audit", LOGS_DIR_K03)
        )