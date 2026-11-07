"""Showcase day: run PharmaFind on this laptop and let visitors use it on their phones.

Double-click start_showcase.bat  (or run:  python showcase.py)

  1. resets the demo data (same as python seed.py)
  2. starts PharmaFind with a real web server (waitress) on http://localhost:5000
  3. opens a free Cloudflare "quick tunnel": a temporary https:// address for phones
     (https is needed for phone cameras). No account needed.
  4. opens the app and a big QR code page in your browser

Leave this window open during the showcase. Stop with Ctrl+C or by closing it.
The https address is different every time you start it, so show the QR page from
this run (not an old printout).
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = 5000
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
# The tunnel's own address, e.g. https://seasonal-deck-organisms-sf.trycloudflare.com
# (not api.trycloudflare.com, which only appears in error messages)
URL_PATTERN = re.compile(r"https://(?!api\.)[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com")
DOWNLOADS = {
    "Windows": ("cloudflared.exe",
                "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"),
    "Linux": ("cloudflared",
              "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"),
}


def say(text=""):
    print(text, flush=True)


def ensure_waitress():
    try:
        import waitress  # noqa: F401
    except ImportError:
        say("Installing the web server (waitress)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "waitress"])


def find_cloudflared():
    """Use cloudflared if it's installed, otherwise download it once into tools/."""
    found = shutil.which("cloudflared")
    if found:
        return found
    system = platform.system()
    if system not in DOWNLOADS:
        say("Please install cloudflared first (Mac: brew install cloudflared).")
        return None
    name, url = DOWNLOADS[system]
    path = os.path.join(TOOLS, name)
    if not os.path.exists(path):
        os.makedirs(TOOLS, exist_ok=True)
        say("Downloading cloudflared from Cloudflare's GitHub page (one time, about 60 MB)...")
        try:
            urllib.request.urlretrieve(url, path + ".part")
            os.replace(path + ".part", path)
            if system != "Windows":
                os.chmod(path, 0o755)
        except Exception as e:
            say(f"  Download failed: {e}")
            return None
    return path


def start_server():
    """PharmaFind with waitress (a real server; Flask's own one is only for development)."""
    os.environ["PHARMAFIND_PRODUCTION"] = "1"     # https cookies: phones reach us over https
    from waitress import serve
    from app import app, recognizer
    if recognizer:
        recognizer.warm_up()
    # The tunnel connects from this computer and tells us the visitor used https.
    threading.Thread(target=serve, args=(app,), daemon=True, kwargs=dict(
        host="127.0.0.1", port=PORT, threads=8, ident="PharmaFind",
        trusted_proxy="*", trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for", "x-forwarded-host"},
    )).start()
    wait_until_up(f"http://localhost:{PORT}/healthz", 30)


def wait_until_up(url, seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def start_tunnel(cloudflared):
    """Start a Cloudflare quick tunnel and return (process, public https address)."""
    log = open(os.path.join(TOOLS, "cloudflared.log"), "w", encoding="utf-8")
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    found = {}

    def read_output():
        for line in proc.stdout:
            log.write(line)
            log.flush()
            m = URL_PATTERN.search(line)
            if m and "url" not in found:
                found["url"] = m.group(0)
    threading.Thread(target=read_output, daemon=True).start()

    end = time.time() + 45
    while time.time() < end and "url" not in found and proc.poll() is None:
        time.sleep(0.3)
    return proc, found.get("url")


def main():
    os.chdir(HERE)
    say("=" * 60)
    say("  PharmaFind - showcase mode")
    say("=" * 60)
    ensure_waitress()

    say("1/4  Resetting the demo data...")
    subprocess.check_call([sys.executable, "seed.py"])

    say(f"2/4  Starting PharmaFind on http://localhost:{PORT} ...")
    start_server()

    say("3/4  Opening a public https address for phones...")
    cloudflared = find_cloudflared()
    proc, public = (None, None)
    if cloudflared:
        proc, public = start_tunnel(cloudflared)

    if public:
        say("     Waiting until the address works (can take ~20 seconds)...")
        wait_until_up(public + "/healthz", 60)
        say("4/4  Opening the app and the QR code page.")
        webbrowser.open(public + "/share")
        webbrowser.open(public + "/")
        say()
        say("  Phones can open:   " + public)
        say("  QR code page:      " + public + "/share")
        say("  Pharmacist login:  " + public + "/pharmacy   (shifa / pharma123)")
    else:
        say("  Could not open a public address (no internet?).")
        say("  PharmaFind still works on this laptop:  http://localhost:%d" % PORT)
        webbrowser.open(f"http://localhost:{PORT}/")
    say()
    say("  Keep this window open. Press Ctrl+C to stop.")
    try:
        warned = False
        while True:
            time.sleep(1)
            if public and proc and proc.poll() is not None and not warned:
                say("  The phone link stopped (internet problem?). The app still works on this laptop.")
                say("  To get a new phone link: close this window and start again.")
                warned = True
    except KeyboardInterrupt:
        pass
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
        say("Stopped.")


if __name__ == "__main__":
    main()
