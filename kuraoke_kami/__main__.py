import atexit
import errno
import shutil
import signal
import subprocess
import sys
import webbrowser

from . import config, doctor, log
from .server import serve


def open_ui(port):
    url = f"http://127.0.0.1:{port}/?display=1"
    for cmd in (["omarchy-launch-webapp", url], ["helium-browser", f"--app={url}"], ["chromium", f"--app={url}"]):
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return
    webbrowser.open(url)


def main():
    cfg = config.load()
    if "--doctor" in sys.argv:
        return print(doctor.report(cfg))
    if "--logs" in sys.argv:
        return print("\n".join(log.tail(80)) or f"(no log yet: {config.LOG_FILE})")
    log.setup()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # so `kill` still lets mpv and the socket be cleaned up
    try:
        app, httpd = serve(cfg)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        print(f"Already running on port {cfg['port']}; opening the screen.")
        return open_ui(cfg["port"])
    log.log.info("started on port %s (remote=%s)", cfg["port"], cfg["remote"])
    atexit.register(app.engine.mpv.close)
    print(f"Kuraoke Kami on http://127.0.0.1:{cfg['port']}/")
    if cfg["remote"]:
        print(f"Phone remote: {app.remote_url()}")
        print(f"  (if the phone can't connect: sudo ufw allow {cfg['port']}/tcp)")
    if "--no-ui" not in sys.argv:
        open_ui(cfg["port"])
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


main()
