import os
import platform

def get_linux_distro_pretty_name() -> str:
    """
    Membaca informasi distro langsung dari file /etc/os-release.
    Mengembalikan nama lengkap (contoh: "Ubuntu 22.04.4 LTS").
    """
    os_release_path = "/etc/os-release"
    if os.path.exists(os_release_path):
        try:
            with open(os_release_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                info = {}
                for line in lines:
                    if "=" in line:
                        key, val = line.strip().split("=", 1)
                        info[key] = val.strip('"\'')
                
                # Utamakan PRETTY_NAME (contoh: "Ubuntu 22.04.4 LTS")
                if "PRETTY_NAME" in info:
                    return info["PRETTY_NAME"]
                
                # Fallback jika PRETTY_NAME tidak ada
                name = info.get("NAME", "Linux")
                version = info.get("VERSION", "")
                return f"{name} {version}".strip()
        except Exception:
            pass

    # Fallback ke platform.system() jika bukan Linux / file tidak ada
    return platform.system()