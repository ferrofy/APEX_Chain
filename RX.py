import socket
import json
import os
from datetime import datetime

Port = 5000
Client_Folder = "Client_Blocks"

def Init_Client_Folder():
    if not os.path.exists(Client_Folder):
        os.makedirs(Client_Folder)

def Get_Server_IP():
    IP = input("Enter Server IP: ").strip()
    return Format_IP(IP)

def Format_IP(IP):
    Parts = IP.split(".")
    
    if len(Parts) != 4:
        print("Invalid IP Format ❌")
        exit()

    for Part in Parts:
        if not Part.isdigit() or not (0 <= int(Part) <= 255):
            print("Invalid IP Range ❌")
            exit()

    return ".".join(Parts)

def Create_Tx():
    return {
        "Tx_Id": "TX777",
        "Data": "Hello Blockchain 😎",
        "Time": str(datetime.now())
    }

def Connect_To_Server(Server_IP):
    Client_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Client_Socket.connect((Server_IP, Port))
    return Client_Socket

def Send_Data(Client_Socket, Data):
    Client_Socket.send(json.dumps(Data).encode())

def Receive_Response(Client_Socket):
    return json.loads(Client_Socket.recv(8192).decode())

def Save_File(File_Name, Content):
    File_Path = os.path.join(Client_Folder, File_Name)
    with open(File_Path, "w") as f:
        f.write(Content)

def Close_Connection(Client_Socket):
    Client_Socket.close()

def Start_Client():
    Init_Client_Folder()

    Server_IP = Get_Server_IP()

    Client_Socket = Connect_To_Server(Server_IP)

    Tx_Data = Create_Tx()

    Send_Data(Client_Socket, Tx_Data)

    Response = Receive_Response(Client_Socket)

    print(Response["Message"])

    Save_File(Response["File_Name"], Response["File_Content"])

    Close_Connection(Client_Socket)

Start_Client()