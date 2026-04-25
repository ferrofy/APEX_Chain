import socket
import json
from datetime import datetime

Server_IP = "127.0.0.1"
Port = 5000

Client_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
Client_Socket.connect((Server_IP, Port))

Tx_Data = {
    "Tx_Id": "TX777",
    "Data": "Hello Blockchain 😎",
    "Time": str(datetime.now())
}

Client_Socket.send(json.dumps(Tx_Data).encode())

Response = Client_Socket.recv(1024).decode()
print(Response)

Client_Socket.close()