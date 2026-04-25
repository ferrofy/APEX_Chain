import socket
import os

Host = "0.0.0.0"
Port = 5000

Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
Server_Socket.bind((Host, Port))
Server_Socket.listen(5)

print("Server Running...")

while True:
    Client_Socket, Addr = Server_Socket.accept()
    print(f"Connected: {Addr}")

    Data = Client_Socket.recv(4096).decode()

    File_Name, Content = Data.split("|||")

    if os.path.exists(File_Name):
        with open(File_Name, "w") as f:
            f.write(Content)
        Client_Socket.send("File Updated".encode())
    else:
        Client_Socket.send("File Not Found".encode())

    Client_Socket.close()