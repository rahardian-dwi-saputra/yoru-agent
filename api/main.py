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

# Menentukan lokasi folder proyek
API_DIR = Path(__file__).resolve().parent
PROJECT_DIR = API_DIR.parent / "ssh-hardening-project"
LOGS_DIR = PROJECT_DIR / "logs"


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


# Model Output Response
class K01Response(BaseModel):
    status: Literal["completed", "pending_confirmation", "cancelled", "error"]
    selected_action: Literal["audit", "hardening", "rollback", "none"]
    requires_confirmation: bool
    confirmation_message: Optional[str] = None
    execution_code: Optional[int] = None
    action_logs: List[Dict[str, Any]] = []


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def run_taskfile_action(action: str) -> int:
    """Execution Layer: Memanggil Taskfile secara asynchronous."""
    process = await asyncio.create_subprocess_exec(
        "task", action,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return process.returncode


def read_action_logs(action: str) -> List[Dict[str, Any]]:
    """Log Parser: Membaca log JSON spesifik action."""
    log_file_path = LOGS_DIR / f"{action}.json"
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
# ENDPOINT MAIN
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
            exec_code = await run_taskfile_action(action_to_execute)
            
            if exec_code != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Hermes Agent gagal mengeksekusi '{action_to_execute}'."
                )

            return K01Response(
                status="completed",
                selected_action=action_to_execute,
                requires_confirmation=False,
                confirmation_message=f"Konfirmasi diterima. Tindakan {action_to_execute} berhasil dieksekusi.",
                execution_code=exec_code,
                action_logs=read_action_logs(action_to_execute)
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
        exec_code = await run_taskfile_action("audit")
        return K01Response(
            status="completed",
            selected_action="audit",
            requires_confirmation=False,
            confirmation_message="Tindakan audit aman dijalankan tanpa konfirmasi.",
            execution_code=exec_code,
            action_logs=read_action_logs("audit")
        )