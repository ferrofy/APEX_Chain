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

def Create_File(Index, Addr):
    File_Name = f"Server_File_{Index}_{Addr[0]}.txt"
    Path = os.path.join(Folder, File_Name)
    Content = f"Server File {Index} Created for {Addr[0]}"

    with open(Path, "w") as f:
        f.write(Content)

    return File_Name, Content

def Handle_Client(Client_Socket, Addr):
    print(f"[CONNECTED] {Addr} - Verifying...")

    try:
        Client_Socket.settimeout(2.0)
        Client_Socket.send("Mine_RX".encode())

        Client_Response = Client_Socket.recv(1024).decode()
        
        if Client_Response != "Mine_TX":
            print(f"[AUTH FAILED] Incorrect Client Password from {Addr}")
            Client_Socket.close()
            return

        Client_Socket.settimeout(None)
        print(f"[AUTH SUCCESS] Handshake complete with {Addr}")

    except:
        print(f"[AUTH FAILED] Connection dropped during handshake with {Addr}")
        Client_Socket.close()
        return

    Index = 1

    while True:
        try:
            File_Name, Content = Create_File(Index, Addr)
            Data = f"{File_Name}|{Content}"
            Client_Socket.send(Data.encode())

            print(f"[SENT] {File_Name} -> {Addr}")

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
    Server_Socket.listen(100)
    Server_Socket.settimeout(10.0)

    print(f"[SERVER RUNNING] IP: {Get_Local_IP()} PORT: {Port}")

    while True:
        try:
            print("[LISTENING] 10-second window for new connections...")
            Client_Socket, Addr = Server_Socket.accept()
            
            Client_Socket.settimeout(None)
            Thread = threading.Thread(target=Handle_Client, args=(Client_Socket, Addr))
            Thread.start()

        except socket.timeout:
            print("[TIMEOUT] No new connections. Sleeping 60 seconds...")
            time.sleep(60)

Start_Server()