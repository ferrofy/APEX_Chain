import os
import sys


PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

from User_Node import Start_User


Start_User()
