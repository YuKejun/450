from struct import *
from socket import *

HOST = 'localhost'
PORT = 29876  # our port from before
ADDR = (HOST, PORT)

# get command to send
line = input("Give your input: ").split()
num_list = [int(i) for i in line]
command = pack("B" * len(num_list), *num_list)

# send command to server
client = socket(AF_INET, SOCK_STREAM)
client.connect((ADDR))
client.send(command)
client.close()