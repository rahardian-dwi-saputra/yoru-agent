# Yoru Agent
Yoru-agent adalah agen otomatis untuk memeriksa dan meningkatkan keamanan server berdasarkan standar CIS. Dibangun menggunakan Hermes-agent dan FastAPI, sistem ini memudahkan pemeriksaan keamanan melalui API, serta mendukung proses audit, hardening, dan rollback. Setiap perubahan konfigurasi tetap berada di bawah kendali manusia agar keamanan server terjaga tanpa mengabaikan risiko operasional.

---

## Dislaimer

This project is an independent open-source automation tool designed for system hardening. It references industry security benchmarks (such as CIS Benchmarks) for compliance mapping purposes only and is not officially endorsed, sponsored, or affiliated with the Center for Internet Security (CIS).

---

## Daftar Katalog CIS Compliance
Yoru-agent menggunakan katalog berikut untuk melakukan audit dan hardening keamanan server berdasarkan standar CIS (Center for Internet Security).

| ID | Referensi CIS | Kategori | Deskripsi Kontrol | Mode |
| --- | --- | --- | --- | --- |
| K01 | 5.1.20 | SSH Security | Ensure sshd PermitRootLogin is disabled | Audit & Hardening |
| K02 | 5.2.14 | SSH Security | Ensure SSH PasswordAuthentication is disabled |	Audit & Hardening |
| K03 | 5.1.13 | SSH Security | Ensure sshd LoginGraceTime is configured | Audit & Hardening |
| K04 | 5.1.16 | SSH Security | Ensure sshd MaxAuthTries is configured | Audit & Hardening |
| K05 | 5.1.6 | SSH Security | Ensure sshd Ciphers are configured	Audit & Hardening |
| K06 | 5.1.7 | SSH Security | Ensure sshd MACs are configured  Audit & Hardening |
| K07 | 5.1.8 | SSH Security | Ensure sshd KexAlgorithms are configured	| Audit & Hardening |
| K08 | 4.1.1.2 | Audit Logging | Ensure auditd service is enabled and active | Audit Only |
| K09 | 4.2.3 | Firewall | Ensure ufw service is enabled | Audit Only |
| K10 | 4.2.7 | Firewall | Ensure ufw default deny firewall policy | Audit Only |
| K11 | 2.1.22 | Network Security | Ensure only approved services are listening on a network interface | Audit Only |
| K12 | 6.1.2.4	| System Logging | Ensure journald Storage is configured | Audit & Hardening |
| K13 | 6.1.1.1 | System Logging | Ensure journald service is enabled and active | Audit & Hardening |
| K14 | 6.1.1.2 | System Logging | Ensure journald log file access is configured | Audit & Hardening |
| K15 | 6.1.2.3 | System Logging | Ensure journald Compress is configured | Audit & Hardening |
| K16 | 3.3.4 | Network Security | Ensure broadcast icmp requests are ignored |	Audit & Hardening |
| K17 | 3.3.5 | Network Security | Ensure icmp redirects are not accepted | Audit & Hardening |
| K18 | 3.3.8 | Network Security | Ensure source routed packets are not accepted | Audit & Hardening |
| K19 | 3.3.10 | Network Security | Ensure tcp syn cookies is enabled | Audit & Hardening |

**Keterangan Kategori**
- SSH Security: Mengamankan akses jarak jauh melalui SSH.
- Audit Logging: Memastikan layanan pencatatan aktivitas keamanan tersedia.
- Firewall: Memeriksa status firewall dan kebijakan lalu lintas jaringan.
- Network Security: Mengamankan layanan jaringan dan perilaku konfigurasi jaringan kernel.
- System Logging: Mengatur penyimpanan, akses, dan pengelolaan log sistem.

**Keterangan Mode**
- Audit & Hardening: Sistem memeriksa konfigurasi dan dapat menerapkan perbaikan otomatis sesuai kebijakan.
- Audit Only: Sistem hanya memeriksa dan melaporkan hasil tanpa mengubah konfigurasi server.



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
sudo chown -R yoru-agent:yoru-agent /home/(nam-user-lama)/yoru-agent
cd /home/(nama-user-lama)/yoru-agent/api
```

### 5. Aktifkan Virtual Environment & Jalankan Server API
Aktifkan environment Python dan jalankan server FastAPI menggunakan `uvicorn`:
```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```