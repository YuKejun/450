from socket import *

def receive_message(conn, length):
    data = b""
    while len(data) < length:
        data += conn.recv(length - len(data))
    assert len(data) == length, "receive_message: receive message of wrong length"
    return data

def send_message(conn, data):
    length_sent = 0
    while length_sent < len(data):
        length_sent += conn.send(data[length_sent:])
    assert length_sent == len(data), "send_message: send message of wrong length"

robot_sockets = {}  # IP -> socket
worker_sockets = {}  # worker_id -> socket