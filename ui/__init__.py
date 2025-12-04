# ui/main_window.py
import sys
from datetime import datetime

from PySide6 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from infrastructure.database import init_db


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)


class EMSSWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EMSS Hydroelectric Resort Simulator (Prototype)")

        # init DB
        init_db()

        # set up simulator
        self.config = SimulationConfig()
        self.sim = EMSSSimulator(self.config)

        # buffers for plotting
        self.times = []
        self.demand = []
        self.hydro = []
        self.battery = []
        self.generator = []

        # UI components
        self.canvas = MplCanvas()
        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.reset_button = QtWidgets.QPushButton("Reset")

        self.start_button.clicked.connect(self.start_sim)
        self.stop_button.clicked.connect(self.stop_sim)
        self.reset_button.clicked.connect(self.reset_sim)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.reset_button)

        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.canvas)
        main_layout.addLayout(button_layout)

        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # timer drives simulation
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)  # ms
        self.timer.timeout.connect(self.tick)

    def start_sim(self):
        self.timer.start()

    def stop_sim(self):
        self.timer.stop()

    def reset_sim(self):
        self.timer.stop()
        self.sim.reset()
        self.times.clear()
        self.demand.clear()
        self.hydro.clear()
        self.battery.clear()
        self.generator.clear()
        self.canvas.ax.clear()
        self.canvas.draw()

    def tick(self):
        record = self.sim.step_once()

        self.times.append(record["time"])
        self.demand.append(record["demand_kw"])
        self.hydro.append(record["hydro_kw"])
        self.battery.append(record["battery_kw"])
        self.generator.append(record["generator_kw"])

        self.canvas.ax.clear()
        self.canvas.ax.plot(self.times, self.demand, label="Demand")
        self.canvas.ax.plot(self.times, self.hydro, label="Hydro")
        self.canvas.ax.plot(self.times, self.battery, label="Battery")
        self.canvas.ax.plot(self.times, self.generator, label="Generator")
        self.canvas.ax.legend()
        self.canvas.ax.set_xlabel("Time")
        self.canvas.ax.set_ylabel("kW")
        self.canvas.ax.set_title("Power Flows (Stub Data)")
        self.canvas.fig.autofmt_xdate()
        self.canvas.draw()
