import socket
import json
import os
from datetime import datetime

Port = 5000
Client_Folder = "Client_Blocks"

def Init_Client_Folder():
    if not os.path.exists(Client_Folder):
        os.makedirs(Client_Folder)

def Get_Local_IP_Base():
    Hostname = socket.gethostname()
    Local_IP = socket.gethostbyname(Hostname)

    Parts = Local_IP.split(".")
    Base_IP = ".".join(Parts[:3])

    return Base_IP

def Scan_For_Server():
    Base_IP = Get_Local_IP_Base()

    print(f"Scanning Network: {Base_IP}.0/24 🔍")

    for i in range(1, 255):
        IP = f"{Base_IP}.{i}"

        try:
            Sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Sock.settimeout(0.3)

            Sock.connect((IP, Port))
            print(f"Server Found At: {IP} ✅")
            return IP

        except:
            continue

    return None

def Create_Tx():
    return {
        "Tx_Id": "TX777",
        "Data": "Hello Blockchain 😎",
        "Time": str(datetime.now())
    }

def Send_Data(Client_Socket, Data):
    Client_Socket.send(json.dumps(Data).encode())

def Receive_Response(Client_Socket):
    return json.loads(Client_Socket.recv(8192).decode())

def Save_File(File_Name, Content):
    File_Path = os.path.join(Client_Folder, File_Name)
    with open(File_Path, "w") as f:
        f.write(Content)

def Start_Client():
    Init_Client_Folder()

    Server_IP = Scan_For_Server()

    if Server_IP is None:
        print("Server Not Found ❌")
        return

    Client_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Client_Socket.connect((Server_IP, Port))

    Tx_Data = Create_Tx()

    Send_Data(Client_Socket, Tx_Data)

    Response = Receive_Response(Client_Socket)

    print(Response["Message"])

    Save_File(Response["File_Name"], Response["File_Content"])

    Client_Socket.close()

Start_Client()