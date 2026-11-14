# Instruksi Pengujian Hasil Hardening (Offensive)
Pengujian dilakukan menggunakan komputer lain yang menjalankan Kali Linux. Jika tidak memiliki komputer tambahan, Anda dapat menggunakan Virtual Machine (VM) yang sudah terpasang Kali Linux.

Pastikan komputer pengujian dapat terhubung ke server melalui jaringan dan Anda mengetahui alamat IP server yang akan diuji.

## 1. Pengujian Katalog K01: Root Tidak Bisa Login Lewat SSH
**Tujuan:** Memastikan akun root tidak dapat digunakan untuk login langsung ke server melalui SSH. 

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh root@IP_Server
```
Ganti IP_Server dengan alamat IP server tujuan. Jika diminta, masukkan password root.

**Indikator Keberhasilan:**
Server harus menolak login meskipun password yang dimasukkan benar. Contoh pesan yang mungkin muncul:
> Permission denied (publickey,password)

## 2. Pengujian Katalog K02: Login SSH Hanya Menggunakan SSH Key
**Tujuan:** Memastikan server tidak menerima login menggunakan password dan hanya mengizinkan autentikasi menggunakan SSH Key. 

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh -o PubkeyAuthentication=no nama_user@IP_Server
```
Ganti nama_user dengan nama akun yang terdaftar di server dan IP_Server dengan alamat IP server tujuan.

**Indikator Keberhasilan:**
Server harus menolak login karena autentikasi menggunakan SSH Key dinonaktifkan dari sisi klien, sedangkan autentikasi password telah dimatikan pada server.
> Permission denied (publickey)

## 3. Pengujian Katalog K03: Membatasi Waktu Login SSH (LoginGraceTime)
**Tujuan:** Memastikan server membatasi waktu yang diberikan kepada pengguna untuk menyelesaikan proses login SSH. Jika batas waktu terlampaui, koneksi akan diputus secara otomatis.

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh nama_user@IP_Server
```
Setelah server meminta password, jangan masukkan apa pun (diamkan saja) dan perhatikan waktunya.

**Indikator Keberhasilan:**
Server harus memutus koneksi secara otomatis setelah melewati batas waktu yang telah dikonfigurasi (misalnya 60 detik). Contoh pesan yang mungkin muncul:
> Connection to IP_Server closed by remote host.

## 4. Pengujian Katalog K04: Membatasi Percobaan Auth SSH (MaxAuthTries)
**Tujuan:** Membatasi jumlah percobaan login SSH yang gagal untuk mencegah upaya menebak password atau mencoba berbagai kunci autentikasi.

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh nama_user@IP_Server
```
Masukkan password yang salah secara berulang kali hingga melewati batas percobaan yang telah dikonfigurasi (misalnya 4 kali).

**Indikator Keberhasilan:**
Server harus menutup koneksi secara otomatis setelah jumlah percobaan gagal mencapai batas yang ditentukan. Contoh pesan yang mungkin muncul:
> Received disconnect from IP_Server: 2: Too many authentication failures.

## 5. Pengujian Katalog K05: Pengaturan Ciphers SSH (Enkripsi Transport)
**Tujuan:** Memastikan SSH hanya menggunakan algoritma enkripsi yang kuat dan tidak mengizinkan algoritma lama yang berisiko, seperti `3des-cbc`.

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh -c 3des-cbc nama_user@IP_Server
```
Perintah tersebut mencoba menghubungkan ke server menggunakan algoritma enkripsi lama.

**Indikator Keberhasilan:**
Server harus menolak koneksi karena algoritma enkripsi tersebut tidak diizinkan. Contoh pesan yang mungkin muncul:
> Unable to negotiate with IP_Server port 22: no matching cipher found.

## 6. Pengujian Katalog K06: Pengaturan MACs SSH (Integritas Pesan)
**Tujuan:** Memastikan SSH menggunakan algoritma MAC (Message Authentication Code) yang kuat untuk menjaga integritas data selama komunikasi berlangsung dan tidak mengizinkan algoritma MAC yang beresiko seperti `hmac-sha1`

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh -o MACs=hmac-sha1 nama_user@IP_Server
```

**Indikator Keberhasilan:**
Server harus menolak koneksi karena algoritma MAC tersebut tidak diizinkan. Contoh pesan yang mungkin muncul:
> Unable to negotiate with IP_Server port 22: no matching MAC found.

## 7. Pengujian Katalog K07: Pengaturan KexAlgorithms SSH (Key Exchange)
**Tujuan:** Memastikan proses pertukaran kunci SSH menggunakan algoritma yang aman dan tidak mengizinkan algoritma lama yang berisiko, seperti `diffie-hellman-group1-sha1`.

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
ssh -o KexAlgorithms=diffie-hellman-group1-sha1 nama_user@IP_Server
```
Perintah tersebut mencoba menghubungkan ke server menggunakan algoritma pertukaran kunci yang sudah usang.

**Indikator Keberhasilan:**
Server harus menolak koneksi karena algoritma pertukaran kunci tersebut tidak diizinkan. Contoh pesan yang mungkin muncul:
> Unable to negotiate with IP_Server port 22: no matching key exchange method found.

## 8. Uji Katalog K08: Layanan Auditd Aktif dan Berjalan
**Tujuan:** Memastikan layanan `auditd` selalu aktif untuk mencatat aktivitas penting pada server, seperti akses file sensitif, perubahan konfigurasi, dan aktivitas pengguna. 

Pertama, periksa status layanan auditd pada server:
```bash
sudo systemctl status auditd
```
Selanjutnya, coba akses file sensitif untuk menghasilkan aktivitas yang dapat diaudit:
```bash
cat /etc/shadow
```
Kemudian, periksa apakah aktivitas tersebut tercatat dalam log audit:
```bash
sudo ausearch -m USER_AUTH -i
```
**Indikator Keberhasilan:**
- Layanan `auditd` berstatus `active` (running).
- Aktivitas yang sesuai dengan aturan audit tercatat dalam `/var/log/audit/audit.log`.
- Percobaan akses file sensitif dapat menghasilkan catatan audit jika aktivitas tersebut telah diatur dalam aturan pemantauan.

## 9. Uji Katalog K09: Pengaturan Akses File Log Journald
**Tujuan:** Membatasi akses ke direktori dan file log sistem agar tidak dapat dibaca atau diubah oleh pengguna biasa tanpa izin.

Login ke server menggunakan akun pengguna biasa yang tidak memiliki hak akses administrator (sudo).

Kemudian, jalankan perintah berikut untuk memeriksa direktori log:
```bash
ls -ld /var/log/journal
```
Selanjutnya, coba baca file log Journald:
```bash
cat /var/log/journal/*/system.journal
```

**Indikator Keberhasilan:**
Sistem harus menolak akses pengguna yang tidak memiliki izin untuk membaca file log. Contoh pesan yang mungkin muncul:
> Permission denied

## 10 Pengujian Katalog K10: Penyimpanan Log Journald Permanen
**Tujuan:** Memastikan systemd-journald menyimpan log secara permanen di media penyimpanan disk, bukan hanya di memori sementara (RAM). Dengan demikian, riwayat audit tetap tersedia setelah server melakukan reboot.

Periksa konfigurasi penyimpanan journald menggunakan perintah:
```bash
sudo systemd-analyze cat-config systemd/journald.conf
```
Pastikan parameter `Storage` menunjukkan nilai `persistent`.

Selanjutnya, buat penanda log untuk pengujian:
```bash
logger -t yoru-agent-test "Yoru-Agent Persistent Log Test"
```
Lakukan reboot server:
```bash
sudo reboot
```
Setelah server kembali aktif, periksa apakah penanda log masih tersimpan:
```bash
sudo journalctl -t yoru-agent-test --no-pager
```
Periksa juga keberadaan direktori penyimpanan log permanen:
```bash
sudo ls -lah /var/log/journal/
```

**Indikator Keberhasilan:**
* Parameter Storage dikonfigurasi dengan nilai persistent.
* Penanda log tetap dapat ditemukan setelah server melakukan reboot.
* Direktori `/var/log/journal/` tersedia dan berisi file log berformat .journal.

**Catatan:** Pengujian reboot memerlukan server dinyalakan kembali. Pastikan tidak ada proses penting yang sedang berjalan sebelum melakukannya.

## 11 Uji Validasi Katalog K10: Konfigurasi Rotasi File Log Journald
**Tujuan:** Memastikan penggunaan ruang disk oleh systemd-journald dibatasi melalui parameter SystemMaxUse dan SystemKeepFree, serta pengelolaan file log dilakukan secara berkala melalui parameter MaxFileSec. Pengaturan ini membantu mencegah penggunaan ruang disk yang berlebihan akibat penumpukan log.

Periksa konfigurasi journald beserta konfigurasi tambahan (drop-in) menggunakan perintah:
```bash
sudo systemd-analyze cat-config systemd/journald.conf
```
Pastikan parameter berikut telah dikonfigurasi sesuai kebijakan keamanan server:
* SystemMaxUse: Membatasi total ruang disk yang digunakan oleh log permanen.
* SystemKeepFree: Menentukan ruang disk minimum yang harus dipertahankan agar tetap tersedia.
* MaxFileSec: Menentukan durasi maksimum sebelum file jurnal diputar (rotate).
Selanjutnya, periksa penggunaan ruang disk oleh journald:
```bash
sudo journalctl --disk-usage
```
Untuk memeriksa file jurnal yang tersedia, jalankan:
```bash
sudo journalctl --header
```

**Indikator Keberhasilan:**
* Parameter `SystemMaxUse`, `SystemKeepFree`, dan `MaxFileSec` telah dikonfigurasi sesuai kebijakan penyimpanan log.
* Penggunaan ruang disk oleh journald dapat dipantau melalui `journalctl --disk-usage`.
* Pengelolaan file jurnal berjalan sesuai batas ukuran dan durasi yang ditetapkan.

**Catatan:** Nilai penggunaan disk yang terlihat saat pengujian belum tentu menunjukkan bahwa rotasi telah terjadi. Rotasi dan penghapusan log lama dilakukan sesuai kondisi serta batas konfigurasi journald.

## 12 Pengujian Katalog K13 dan K14: Memastikan Firewall UFW Aktif dan Memblokir Akses yang Tidak Diizinkan
**Tujuan:** Memastikan firewall UFW aktif dan hanya mengizinkan koneksi ke port yang memang diperlukan. Port lainnya harus diblokir agar tidak dapat diakses sembarangan dari jaringan luar.

Dari komputer Kali Linux, jalankan perintah berikut:
```bash
nmap -sV -p- IP_Server
```
Ganti IP_Server dengan alamat IP server tujuan.

**Keterangan perintah:**
* -sV: Mendeteksi layanan dan versinya pada port yang terbuka.
* -p-: Memindai seluruh port, mulai dari 1 hingga 65535.

**Indikator Keberhasilan:**
* Port yang tidak diizinkan berstatus filtered atau closed.
* Hanya port yang secara khusus diizinkan, seperti port 22 untuk SSH atau port aplikasi web, yang berstatus open.

**Indikator Kegagalan:**

Terdapat port yang berstatus open, padahal port tersebut tidak seharusnya dapat diakses dari jaringan luar.

## 13 Pengujian Katalog K15 Membatasi Layanan Jaringan agar Hanya Mendengarkan Interface yang Diizinkan
**Tujuan:** Memastikan layanan internal hanya menerima koneksi melalui interface jaringan yang diizinkan, misalnya localhost, sehingga tidak dapat diakses langsung dari jaringan luar.

Pertama, periksa port dan alamat IP yang digunakan oleh layanan pada server:
```bash
sudo ss -tulnp
```
Perhatikan alamat IP yang ditampilkan:
* 127.0.0.1:[port]: Layanan hanya menerima koneksi dari komputer itu sendiri.
* 0.0.0.0:[port]: Layanan menerima koneksi melalui seluruh interface IPv4.
* [::]:[port]: Layanan menerima koneksi melalui seluruh interface IPv6.

Selanjutnya, dari komputer Kali Linux, uji apakah port layanan tersebut dapat diakses:
```bash
nmap -sV -p NOMOR_PORT IP_Server
```
Ganti NOMOR_PORT dengan port layanan yang ingin diuji dan IP_Server dengan alamat IP server tujuan.

**Indikator Keberhasilan:**
Port layanan yang seharusnya hanya dapat diakses secara lokal tidak dapat diakses dari komputer lain. Hasil pemindaian menunjukkan status `filtered` atau `closed`.

**Indikator Kegagalan:**
Port layanan internal berstatus `open` dan dapat diakses dari jaringan luar, padahal layanan tersebut seharusnya hanya menerima koneksi lokal.

## 14. Pengujian Katalog K16: Pengabaian Permintaan ICMP Broadcast
**Tujuan:** Memastikan server tidak merespons permintaan ping yang dikirim ke alamat broadcast jaringan. Pengaturan ini membantu mencegah serangan Smurf Attack yang memanfaatkan respons ICMP dari perangkat dalam jaringan.

Pertama, cari alamat broadcast jaringan pada server dengan menjalankan perintah berikut:
```bash
ip -4 addr
```
Perhatikan alamat broadcast yang ditampilkan pada interface jaringan server.

Selanjutnya, dari komputer Kali Linux yang berada pada jaringan yang sama, kirim permintaan ping ke alamat broadcast tersebut:
```bash
ping -b IP_Broadcast_Server
```
Ganti IP_Broadcast_Server dengan alamat broadcast jaringan server.

**Indikator Keberhasilan:**
Server tidak memberikan respons terhadap permintaan ICMP Echo Request yang dikirim ke alamat broadcast.

**Indikator Kegagalan:**
Server memberikan respons terhadap permintaan ping broadcast tersebut.

## 15. Katalog K17: Penolakan ICMP Redirect
**Tujuan:** Memastikan server mengabaikan pesan ICMP Redirect yang dapat digunakan untuk mengubah jalur komunikasi jaringan tanpa izin.

Dari komputer Kali Linux yang berada pada jaringan yang sama, kirim paket ICMP Redirect menggunakan perintah berikut:
```bash
sudo hping3 --icmp --icmptype 5 --icmpcode 1 -a IP_Gateway_Palsu IP_Server
```
**Ganti:**
* IP_Gateway_Palsu: Alamat IP sumber palsu yang digunakan dalam pengujian.
* IP_Server: Alamat IP server yang menjadi target pengujian.
**Penjelasan Parameter:**
* --icmp: Mengirim paket menggunakan protokol ICMP.
* --icmptype 5: Menentukan jenis pesan ICMP Redirect.
* --icmpcode 1: Menentukan kode ICMP Redirect untuk host.
* -a: Mengatur alamat IP sumber paket.

Bandingkan hasil kedua pemeriksaan tersebut.

**Indikator Keberhasilan:**
Tabel routing server tidak mengalami perubahan akibat pesan ICMP Redirect yang dikirim selama pengujian.

**Indikator Kegagalan:**
Terdapat perubahan jalur routing yang disebabkan oleh penerimaan pesan ICMP Redirect dari sumber yang tidak dipercaya.

## 16. Pengujian Katalog K18: Penolakan Source Routed Packets
**Tujuan:** Memastikan server menolak paket jaringan yang jalur pengirimannya ditentukan oleh pengirim (Source Routing). Pengaturan ini mencegah pihak tidak berwenang mengarahkan paket melalui jalur tertentu untuk menghindari pembatasan jaringan.

Pengujian dilakukan menggunakan komputer Kali Linux yang telah terpasang Python dan library Scapy.

Buat file Python, misalnya `test_source_routing.py`, kemudian isi dengan kode berikut:
```python
from scapy.all import IP, TCP, send

# Alamat IP server tujuan
target_ip = "IP_Server"

# Membuat paket dengan opsi Source Routing (LSRR)
packet = (
    IP(
        dst=target_ip,
        options=[("LSRR", ["8.8.8.8", target_ip])]
    )
    / TCP(dport=22, flags="S")
)

# Mengirim paket pengujian
send(packet, verbose=False)

print("[*] Paket Source Routing telah dikirim.")
```
Ganti IP_Server dengan alamat IP server tujuan.

Jalankan program menggunakan perintah:
```bash
sudo python3 test_source_routing.py
```

Selanjutnya, periksa log kernel pada server untuk melihat apakah terdapat catatan terkait paket yang ditolak:
```bash
sudo dmesg --follow
```

**Indikator Keberhasilan:**
Server tidak menerima atau memproses paket dengan opsi Source Routing yang tidak diizinkan. Jika tersedia, log kernel dapat digunakan sebagai bukti pendukung adanya paket yang ditolak.

## 17. Pengujian Katalog K19: Pengaktifan TCP SYN Cookies
**Tujuan:** Mengaktifkan perlindungan TCP SYN Cookies untuk membantu server menghadapi serangan SYN Flood, yaitu serangan yang membanjiri server dengan permintaan koneksi TCP sehingga sumber daya server terkuras.

Pengujian dilakukan dari komputer Kali Linux dengan mengirimkan sejumlah paket SYN ke port layanan yang terbuka pada server.

Gunakan perintah berikut untuk pengujian terbatas:
```bash
sudo hping3 -c 300 -d 120 -S -w 64 -p 8000 IP_Server
```
Ganti IP_Server dengan alamat IP server tujuan dan 8000 dengan port layanan yang ingin diuji.
**Keterangan parameter:**
* -c 300: Mengirim maksimal 300 paket.
* -d 120: Mengatur ukuran data paket sebesar 120 byte.
* -S: Mengirim paket dengan flag SYN.
* -w 64: Mengatur ukuran TCP window.
* -p 8000: Menentukan port tujuan.
Selama pengujian berlangsung, periksa apakah layanan server masih dapat diakses. Misalnya, coba akses dashboard Yoru-Agent atau lakukan koneksi SSH dari komputer lain.

Untuk memeriksa apakah TCP SYN Cookies aktif, jalankan perintah berikut pada server:
```bash
sysctl net.ipv4.tcp_syncookies
```

**Indikator Keberhasilan:**
* Nilai `net.ipv4.tcp_syncookies` menunjukkan 1.
* Server tetap dapat menerima koneksi normal selama pengujian berlangsung.
* Layanan yang diuji tetap berjalan dan dapat diakses.

**Indikator Kegagalan:**
Nilai TCP SYN Cookies tidak aktif atau layanan server mengalami gangguan ketika menerima lonjakan permintaan koneksi.