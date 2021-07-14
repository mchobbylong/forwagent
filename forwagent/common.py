import select
import os
import subprocess
from urllib.parse import unquote


BUF_SIZE = 4096
TYPE_SSH = b"SSH"
TYPE_GPG = b"GPG"


CONF_DIR = os.path.join(os.path.expanduser("~"), ".forwagent")
TRUSTED = os.path.join(CONF_DIR, "trusted.pem")
KEY = os.path.join(CONF_DIR, "key.pem")
CERT = os.path.join(CONF_DIR, "cert.pem")


def get_gpg_dirs():
    p = subprocess.run(["gpgconf", "--list-dirs"], stdout=subprocess.PIPE, check=True)
    return dict(line.split(":", 1) for line in unquote(p.stdout.decode()).splitlines())


def forward(sockets, a, b):
    data = a.recv(BUF_SIZE)
    if data:
        b.sendall(data)
    else:
        for s in (a, b):
            if sockets.pop(s, None):
                s.close()


def run(sockets):
    while True:
        readable, _, _ = select.select(sockets, [], [])
        for s, f in list(sockets.items()):
            if s in readable:
                try:
                    f(s)
                except Exception as e:
                    print("Error", e)
