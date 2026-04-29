import os
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PYTHON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Files", "Python")
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


def show_menu():
    print()
    print("=" * 72)
    print("FerroFy - Local WiFi Blockchain System")
    print("=" * 72)
    print("1. User Node  - dark GUI form, sends data to one Doc Node")
    print("2. Doc Node   - dark GUI approval station")
    print("3. Data Node  - terminal blockchain storage and peer majority repair")
    print("Q. Quit")
    print("=" * 72)


def main():
    while True:
        show_menu()
        choice = input("> ").strip().lower()

        if choice == "1":
            from User_Node import Start_User

            Start_User()
            break
        if choice == "2":
            from Doc_Node import Start_Doc

            Start_Doc()
            break
        if choice == "3":
            from Data_Node import Start_Data

            Start_Data()
            break
        if choice in {"q", "quit", "exit"}:
            print("Goodbye.")
            break

        print("Invalid choice. Enter 1, 2, 3, or Q.")


if __name__ == "__main__":
    main()
