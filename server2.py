from socket_utility import *
from struct import *
import threading
from socket import *
from server_utility import *
import select

# PORT = 29876
PORT = 29876

# existing clients sockets, including robots and apps
sockets = {}  # conn -> addr


# open the server socket for connection
serv = socket(AF_INET, SOCK_STREAM)
serv.bind(('', PORT))
serv.listen(5)
print("listening ...")
while True:
    select_result = select.select([serv] + list(sockets.keys()), [], [], 0)[0]
    for evented_conn in select_result:
        if evented_conn == serv:
            (conn, client_addr) = serv.accept()
            print("serving", client_addr)
            sockets[conn] = client_addr
        else:
            data = receive_message(evented_conn, 1)
            command_type = unpack("B", data)[0]
            command_funcs[command_type](evented_conn, sockets[evented_conn])

