from socket_utility import *
from struct import *
import threading
from socket import *
from server_utility import *

# PORT = 29876
PORT = 29876

# serving a client
def serve_client(conn, addr):
    while True:
        data = receive_message(conn, 1)
        command_type = unpack("B", data)[0]
        command_funcs[command_type](conn, addr)
    conn.close()


# open the server socket for connection
serv = socket(AF_INET, SOCK_STREAM)
serv.bind(('', PORT))
serv.listen(5)
print("listening ...")
while True:
    (conn, client_addr) = serv.accept()
    print("serving " + str(client_addr))
    t = threading.Thread(target=serve_client, args=(conn, client_addr))
    t.start()
