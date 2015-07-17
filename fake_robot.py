from struct import *
from socket import *
import sys
import select

HOST = 'localhost'
# PORT = 29876  # our port from before
PORT = 29876
ADDR = (HOST, PORT)


# send command to server
client = socket(AF_INET, SOCK_STREAM)
client.connect((ADDR))
while True:
    select_result = select.select([sys.stdin, client], [], [], 0)[0]
    if sys.stdin in select_result:
        # get command to send
        line = sys.stdin.readline().split()
        num_list = [int(i) for i in line]
        command = pack("B" * len(num_list), *num_list)
        client.sendall(command)
        # if apply for crossing, block until get permit
        if num_list[0] == 6:
            data = client.recv(1)
            reply = unpack("B", data)[0]
            while reply != 1:
                data = client.recv(6)
                (type, from_x, from_y, to_x, to_y, route_length) = unpack("B" * 6, data)
                data = client.recv(route_length)
                if type == 0:
                    data = client.recv(4)

                data = client.recv(1)
                reply = unpack("B", data)[0]
            print("Go!")
        # if worker apply to join, block to receive accept or reject
        elif num_list[0] == 13:
            reply = unpack("B", client.recv(1))[0]
            if reply == 2:
                print("request accepted")
            elif reply == 3:
                print("request denied")
            else:
                raise Exception("Unrecognized reply")
    elif client in select_result:
        # if have received a route
        command_type = unpack("B", client.recv(1))[0]
        if command_type == 0:
            data_list = unpack("B" * 6, client.recv(6))
            print(data_list)
            route_type = data_list[0]
            route_length = data_list[5]
            client.recv(route_length)
            if route_type == 0:
                client.recv(4)
            # TODO: true reply; currently reply everything fine for any case
            client.sendall(pack("B", 1))
client.close()
