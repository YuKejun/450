from socket import *

def receive_message(conn, length):
    data = b""
    while len(data) < length:
        received_data = conn.recv(length - len(data))
        # assert received_data, "Connection " + str(conn) + "closed"
        if not received_data:
            raise error("Connection " + conn.getpeername()[0] + " closed")
        data += received_data
    assert len(data) == length, "receive_message: receive message of wrong length"
    return data

def send_message(conn, data):
    length_sent = 0
    while length_sent < len(data):
        length_sent += conn.send(data[length_sent:])
    assert length_sent == len(data), "send_message: send message of wrong length"

robot_sockets = {}  # robot IP -> socket
worker_sockets = {}  # dock id -> socket