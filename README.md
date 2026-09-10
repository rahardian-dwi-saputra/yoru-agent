# Yoru Agent
yoru-agent adalah agen berbasis Hermes-agent yang dirancang untuk melakukan hardening atau pengerasan keamanan server secara otomatis sesuai standar kepatuhan CIS (Center for Internet Security). Sistem ini menyediakan antarmuka FastAPI berbasis Python yang memungkinkan proses pengerasan server dipicu dan dikelola dengan mudah melalui integrasi API. Dengan mengombinasikan otomatisasi kepatuhan CIS dan kepraktisan FastAPI, agen ini membantu menjaga infrastruktur server tetap aman, terstandarisasi, dan efisien untuk diintegrasikan ke dalam alur kerja DevOps.

## Requirement
Sebelum menjalankan proyek pastikan di komputer anda sudah terinstall:
- [Hermes Agent](https://github.com/nousresearch/hermes-agent)
- Open SSH Server
- Dependensi: `python3-venv`

---

## Cara Instalasi & Penggunaan
Ikuti langkah-langkah di bawah ini untuk menjalankan proyek di komputer lokal:
### 1. Unduh Proyek (Clone Repository)
Salin (clone) repository ini ke komputer Anda, lalu masuk ke direktori proyek:
```bash
git clone https://github.com/rahardian-dwi-saputra/yoru-agent.git
cd yoru-agent
```
### 2. Jalankan Script Setup
Masuk ke folder setup, berikan izin eksekusi pada skrip, lalu jalankan untuk menyiapkan virtual environment dan memasang `hermes-agent`:
```bash
cd setup
chmod +x setup.sh
./setup.sh
chmod +x setup_hermes_agent
sudo ./setup_hermes_agent
```
### 3. Masuk sebagai User `yoru-agent`
Skrip setup otomatis membuat pengguna sistem baru bernama `yoru-agent`. Beralihlah ke pengguna tersebut untuk menjalankan aplikasi:
```bash
sudo su - yoru-agent
```
### 4. Masuk ke Folder API
Pindah ke direktori api yang berada di dalam folder proyek Anda:
> Catatan: Ganti (nama-user-lama) dengan nama username utama komputer Anda sebelumnya tempat folder proyek diunduh.
```bash
cd /home/(nama-user-lama)/yoru-agent/api
```

### 5. Aktifkan Virtual Environment & Jalankan Server API
Aktifkan environment Python dan jalankan server FastAPI menggunakan `uvicorn`:
```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```