import socket

Server_IP = "192.168.1.5"
Port = 5000

Client_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
Client_Socket.connect((Server_IP, Port))

File_Name = "test.txt"
New_Content = "Hello From Other Computer 😎"

Data = File_Name + "|||" + New_Content

Client_Socket.send(Data.encode())

Response = Client_Socket.recv(1024).decode()
print(Response)

Client_Socket.close()