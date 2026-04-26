import socket
import os
import threading

Port = 5000
Folder = "Blocks"

def Init_Folder():
    if not os.path.exists(Folder):
        os.makedirs(Folder)

def Get_Server_IP():
    return input("Enter Server IP: ").strip()

def Connect(Server_IP):
    Sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Sock.connect((Server_IP, Port))
    return Sock

def Save_File(File_Name, Content):
    Path = os.path.join(Folder, File_Name)

    with open(Path, "w") as f:
        f.write(Content)

def Receive_Loop(Sock):
    while True:
        try:
            Data = Sock.recv(8192).decode()

            if not Data:
                break

            File_Name, Content = Data.split("|")

            Save_File(File_Name, Content)

            print(f"[RECEIVED] {File_Name}")

        except:
            print("[ERROR] Connection Lost")
            break

def Send_Loop(Sock):
    Index = 1

    while True:
        try:
            File_Name = f"Client_File_{Index}.txt"
            Content = f"Client File {Index}"

            Data = f"{File_Name}|{Content}"
            Sock.send(Data.encode())

            print(f"[SENT] {File_Name}")

            Index += 1

        except:
            break

def Start_Client():
    Init_Folder()

    Server_IP = Get_Server_IP()
    Sock = Connect(Server_IP)

    print("[CONNECTED TO SERVER]")

    threading.Thread(target=Receive_Loop, args=(Sock,)).start()
    threading.Thread(target=Send_Loop, args=(Sock,)).start()

Start_Client()