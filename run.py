import subprocess
import sys
import time
import os
import winreg
import ctypes
import webbrowser

def set_windows_proxy(enable: bool, server: str = "127.0.0.1:8080"):
    """Enable or disable Windows System Proxy via the Registry"""
    try:
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE)
        
        # 1 to enable, 0 to disable
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        
        if enable:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
            
        winreg.CloseKey(key)
        
        # Notify the OS to apply the changes immediately so we don't have to restart browsers
        INTERNET_OPTION_REFRESH = 37
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        internet_set_option(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        internet_set_option(0, INTERNET_OPTION_REFRESH, 0, 0)
        
    except Exception as e:
        print(f"⚠️ Could not modify Windows Proxy automatically: {e}")

def main():
    print("=======================================")
    print("🚀 Starting Network Monitor...")
    print("=======================================\n")
    
    venv_dir = os.path.join(os.path.dirname(__file__), "venv", "Scripts")
    python_exe = os.path.join(venv_dir, "python.exe")
    mitmdump_exe = os.path.join(venv_dir, "mitmdump.exe")

    print("[1/4] Starting Backend UI Server...")
    server_process = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "backend.server:app", "--port", "8000"],
        cwd=os.path.dirname(__file__)
    )
    
    time.sleep(1.5)

    print("[2/4] Starting MITM Proxy Interceptor...")
    proxy_process = subprocess.Popen(
        [mitmdump_exe, "-s", "backend/proxy.py", "--listen-port", "8080"],
        cwd=os.path.dirname(__file__)
    )

    time.sleep(1)

    print("[3/4] Enabling Windows System Proxy (127.0.0.1:8080)...")
    set_windows_proxy(enable=True)
    print("✅ System Proxy Enabled")

    print("[4/4] Opening Web Dashboard...")
    time.sleep(1)
    webbrowser.open("http://localhost:8000")

    print("\n✅ ALL SYSTEMS GO! Intercepting internet traffic.")
    print("⚠️  IMPORTANT: Keep this window open while monitoring!")
    print("🛑 To safely stop monitoring and restore your internet, click here and press CTRL+C.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down gracefully...")
        
        # Restore proxy so internet doesn't break
        print("🔧 Reverting Windows System Proxy settings to normal...")
        set_windows_proxy(enable=False)
        print("✅ System Proxy Disabled")

        print("🛑 Closing background servers...")
        proxy_process.terminate()
        server_process.terminate()
        
        proxy_process.wait()
        server_process.wait()
        
        print("✅ Network Monitor safely shut down. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
