import os
import sys


PYTHON_DIR = os.path.dirname(os.path.abspath(__file__))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

from Doc_Node import Start_Doc


Start_Doc()
