from struct import *
from socket import *
import select
import sys
import socket_utility

# PORT = 29876
PORT = 29876


# open the server socket for connection
serv = socket(AF_INET, SOCK_STREAM)
serv.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
serv.bind(('', PORT))
serv.listen(5)
print("listening ...")
(conn, client_addr) = serv.accept()
print("serving", client_addr)
conn.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)
while True:
    (read_events, write_events, error_events) = select.select([sys.stdin, conn], [], [conn], 0)
    for evented_conn in read_events:
        if evented_conn == sys.stdin:
            line = sys.stdin.readline().split()
            num_list = [int(i) for i in line]
            command = pack("B" * len(num_list), *num_list)
            conn.sendall(command)
        else:
            data = socket_utility.receive_message(evented_conn, 1)
            message = unpack("B", data)[0]
            # if message != 16:
            #     print(message)
            print(message)


