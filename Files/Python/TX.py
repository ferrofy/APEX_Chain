import socket
import os
import threading
import time

Host = "0.0.0.0"
Port = 5000

Folder = "Blocks"

def Init_Folder():
    if not os.path.exists(Folder):
        os.makedirs(Folder)

def Get_Local_IP():
    return socket.gethostbyname(socket.gethostname())

def Create_File(Index):
    File_Name = f"File_{Index}.txt"
    Path = os.path.join(Folder, File_Name)

    Content = f"File {Index} Created"

    with open(Path, "w") as f:
        f.write(Content)

    return File_Name, Content

def Handle_Client(Client_Socket, Addr):
    print(f"[CONNECTED] {Addr}")

    Index = 1

    while True:
        try:
            File_Name, Content = Create_File(Index)

            Data = f"{File_Name}|{Content}"
            Client_Socket.send(Data.encode())

            print(f"[SENT] {File_Name} → {Addr}")

            Index += 1
            time.sleep(10)

        except:
            print(f"[DISCONNECTED] {Addr}")
            Client_Socket.close()
            break

def Start_Server():
    Init_Folder()

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(5)

    print(f"[SERVER RUNNING] Your IP: {Get_Local_IP()} PORT: {Port} \nEnter Your Server IP:" , end=" ")

    while True:
        Client_Socket, Addr = Server_Socket.accept()

        Thread = threading.Thread(target=Handle_Client, args=(Client_Socket, Addr))
        Thread.start()

Start_Server()