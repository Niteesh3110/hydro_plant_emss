# app.py
import sys
from PySide6 import QtWidgets
from ui.main_window import EMSSWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = EMSSWindow()
    window.resize(1000, 600)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
