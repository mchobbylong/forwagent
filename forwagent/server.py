from .common import (
    BUF_SIZE,
    TYPE_SSH,
    TYPE_GPG,
    forward,
    run,
    KEY,
    CERT,
    TRUSTED,
    get_gpg_dir,
)
import paramiko
import subprocess
import socket
import ssl

import logging

logger = logging.getLogger(__name__)


def ensure_agent():
    proc = subprocess.run(["gpg-connect-agent", "/bye"], check=False, capture_output=True)
    output = proc.stderr.decode().splitlines()
    if not output:
        logger.debug("Ensure gpg agent by calling gpg-connect-agent: (empty output)")
    else:
        logger.debug("Ensure gpg agent by calling gpg-connect-agent:")
        for line in output:
            logger.debug(line)


def get_ssh_agent():
    ensure_agent()
    agent = paramiko.Agent()
    conn = agent._conn
    if conn is None:
        logger.error("No SSH agent available")
    return conn


def get_gpg_agent(agent_socket):
    ensure_agent()
    with open(agent_socket, "rb") as f:
        port, nonce = f.read().split(b"\n", 1)
    agent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    agent.connect(("127.0.0.1", int(port)))
    agent.sendall(nonce)
    return agent


def main(server_addr):
    agent_socket = get_gpg_dir("agent-socket")
    sockets = {}

    def forward_to(b):
        return lambda a: forward(sockets, a, b)

    def forward_ssh(agent):
        def inner(client):
            data = client.recv(BUF_SIZE)
            if data:
                agent.send(data)
                client.sendall(agent.recv(BUF_SIZE))
            else:
                client.close()
                agent.close()
                sockets.pop(client)

        return inner

    def accept(sock):
        client, _ = sock.accept()
        data = client.recv(3)
        if data == TYPE_SSH:
            agent = get_ssh_agent()
            sockets[client] = forward_ssh(agent)
        elif data == TYPE_GPG:
            agent = get_gpg_agent(agent_socket)
            sockets[agent] = forward_to(client)
            sockets[client] = forward_to(agent)
        else:
            logger.info("Connection of unknown type: %r", data)
            client.close()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(TRUSTED)
    context.load_cert_chain(CERT, KEY)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(server_addr)
    server.listen()
    logger.info("Server listening on %s:%d", *server_addr)
    with context.wrap_socket(server, server_side=True) as ssock:
        sockets[ssock] = accept

        run(sockets)
