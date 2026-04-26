import socket
import json
import hashlib
import os
from datetime import datetime

Host = "0.0.0.0"
Port = 5000

Data_Folder = "Blocks"
Index_File = "Blocks/Index.json"
Test_File = "Blocks/Test.txt"

def Init_Folder():
    if not os.path.exists(Data_Folder):
        os.makedirs(Data_Folder)

    if not os.path.exists(Index_File):
        with open(Index_File, "w") as f:
            json.dump({}, f)

def Calculate_Hash(Block_Data):
    Block_String = json.dumps(Block_Data, sort_keys=True).encode()
    return hashlib.sha256(Block_String).hexdigest()

def Get_Last_Block():
    Files = sorted(os.listdir(Data_Folder))
    Files = [f for f in Files if f.startswith("block_")]

    if not Files:
        return None

    with open(os.path.join(Data_Folder, Files[-1]), "r") as f:
        return json.load(f)

def Create_Test_File():
    with open(Test_File, "w") as f:
        f.write("Successfully Connected")

def Create_Block(Tx_Data):
    Last_Block = Get_Last_Block()

    Index = 1 if Last_Block is None else Last_Block["Index"] + 1
    Prev_Hash = "0" if Last_Block is None else Last_Block["Hash"]

    Block = {
        "Index": Index,
        "Timestamp": str(datetime.now()),
        "Tx_Id": Tx_Data["Tx_Id"],
        "Data": Tx_Data["Data"],
        "Prev_Hash": Prev_Hash
    }

    Block["Hash"] = Calculate_Hash(Block)

    File_Name = f"block_{Index}.json"
    File_Path = os.path.join(Data_Folder, File_Name)

    with open(File_Path, "w") as f:
        json.dump(Block, f, indent=4)

    Update_Index(Tx_Data["Tx_Id"], File_Name)

    return Block

def Update_Index(Tx_Id, File_Name):
    with open(Index_File, "r") as f:
        Index_Map = json.load(f)

    Index_Map[Tx_Id] = File_Name

    with open(Index_File, "w") as f:
        json.dump(Index_Map, f, indent=4)

def Read_File_Content(File_Path):
    with open(File_Path, "r") as f:
        return f.read()

def Handle_Client(Client_Socket):
    Data = Client_Socket.recv(8192).decode()
    Tx_Data = json.loads(Data)

    Create_Test_File()
    Block = Create_Block(Tx_Data)

    File_Content = Read_File_Content(Test_File)

    Response = {
        "Message": f"Block {Block['Index']} Added",
        "File_Name": "Test.txt",
        "File_Content": File_Content
    }

    Client_Socket.send(json.dumps(Response).encode())
    Client_Socket.close()

def Start_Server():
    Init_Folder()

    Server_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    Server_Socket.bind((Host, Port))
    Server_Socket.listen(5)

    print("Blockchain Server Running...")

    while True:
        Client_Socket, Addr = Server_Socket.accept()
        print(f"Connected: {Addr}")
        Handle_Client(Client_Socket)

Start_Server()