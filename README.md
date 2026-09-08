# Yoru Agent

## Cara Instalasi & Penggunaan
Ikuti langkah-langkah di bawah ini untuk menjalankan proyek di komputer lokal:
### 1. Clone Repository
Unduh kode sumber dan masuk ke folder proyek:
```bash
git clone https://github.com/rahardian-dwi-saputra/yoru-agent.git
cd yoru-agent
```
### 2. Jalankan Script Setup & Hermes Agent
Masuk ke folder setup untuk menyiapkan virtual environment dan memasang `hermes-agent`:
```bash
cd setup
chmod +x setup.sh
./setup.sh
chmod +x setup_hermes_agent
sudo ./setup_hermes_agent
```
### 3. Aktifkan Environment & Jalankan API
Kembali ke root proyek, berpindah ke folder `api`, lalu jalankan server FastAPI:
```bash
cd ../api
source venv/bin/activate
uvicorn main:app --reload --port 8000
```