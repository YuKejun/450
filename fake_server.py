from struct import *
from socket import *
import select
import sys
import socket_utility

# PORT = 29876
PORT = 29874




# open the server socket for connection
serv = socket(AF_INET, SOCK_STREAM)
serv.bind(('', PORT))
serv.listen(5)
print("listening ...")
(conn, client_addr) = serv.accept()
print("serving", client_addr)
while True:
    select_result = select.select([sys.stdin, conn], [], [], 0)[0]
    for evented_conn in select_result:
        if evented_conn == sys.stdin:
            line = sys.stdin.readline().split()
            num_list = [int(i) for i in line]
            command = pack("B" * len(num_list), *num_list)
            conn.sendall(command)
        else:
            data = socket_utility.receive_message(evented_conn, 1)
            print(unpack("B", data)[0])

