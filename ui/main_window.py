# ui/main_window.py
import sys
from datetime import datetime

from PySide6 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from domain.simulation import EMSSSimulator, SimulationConfig
from infrastructure.database import init_db


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)

class HydroTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.canvas = MplCanvas()

        self.times = []
        self.hydro = []
        self.reservoir = []

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.canvas)

        # Optional: labels for current values
        self.label_current = QtWidgets.QLabel("Hydro: - kW | Reservoir: - m³")
        layout.addWidget(self.label_current)

        self.setLayout(layout)

    def update_with_record(self, record: dict):
        self.times.append(record["time"])
        self.hydro.append(record["hydro_kw"])
        self.reservoir.append(record["reservoir_level_m3"])

        ax = self.canvas.ax
        ax.clear()

        ax.plot(self.times, self.hydro, label="Hydro (kW)")
        ax.set_xlabel("Time")
        ax.set_ylabel("Hydro Power (kW)")

        # Reservoir level on a 2nd y-axis
        ax2 = ax.twinx()
        ax2.plot(self.times, self.reservoir, color="tab:green", label="Reservoir (m³)")
        ax2.set_ylabel("Reservoir Level (m³)")

        # Build combined legend
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc="upper left")

        self.canvas.fig.autofmt_xdate()
        self.canvas.draw()

        self.label_current.setText(
            f"Hydro: {record['hydro_kw']:.1f} kW | Reservoir: {record['reservoir_level_m3']:.0f} m³"
        )

    def reset(self):
        self.times.clear()
        self.hydro.clear()
        self.reservoir.clear()
        self.canvas.ax.clear()
        self.canvas.draw()
        self.label_current.setText("Hydro: - kW | Reservoir: - m³")

# ---------- Resort Tab ----------

class ResortTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.canvas = MplCanvas()

        self.times = []
        self.demand = []
        self.battery_power = []
        self.battery_soc = []

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.canvas)

        self.label_current = QtWidgets.QLabel("Demand: - kW | Battery: - kW | SoC: - %")
        layout.addWidget(self.label_current)

        self.setLayout(layout)

    def update_with_record(self, record: dict):
        self.times.append(record["time"])
        self.demand.append(record["demand_kw"])
        self.battery_power.append(record["battery_kw"])
        self.battery_soc.append(record["battery_soc"] * 100.0)

        ax = self.canvas.ax
        ax.clear()

        ax.plot(self.times, self.demand, label="Demand (kW)")
        ax.plot(self.times, self.battery_power, label="Battery Power (kW)")

        ax.set_xlabel("Time")
        ax.set_ylabel("Power (kW)")

        # Battery SoC on second y-axis
        ax2 = ax.twinx()
        ax2.plot(self.times, self.battery_soc, color="tab:green", label="Battery SoC (%)")
        ax2.set_ylabel("Battery SoC (%)")

        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc="upper left")

        self.canvas.fig.autofmt_xdate()
        self.canvas.draw()

        self.label_current.setText(
            f"Demand: {record['demand_kw']:.1f} kW | Battery: {record['battery_kw']:.1f} kW | SoC: {record['battery_soc']*100:.1f} %"
        )

    def reset(self):
        self.times.clear()
        self.demand.clear()
        self.battery_power.clear()
        self.battery_soc.clear()
        self.canvas.ax.clear()
        self.canvas.draw()
        self.label_current.setText("Demand: - kW | Battery: - kW | SoC: - %")


# ---------- Telemetry Tab ----------

class TelemetryTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Time", "Step", "Demand (kW)", "Hydro (kW)",
            "Battery (kW)", "Gen (kW)", "Spilled (kW)",
            "Unserved (kW)", "Battery SoC (%)"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.table)
        self.setLayout(layout)

    def update_with_record(self, record: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)

        values = [
            record["time"].strftime("%H:%M"),
            str(record["step"]),
            f"{record['demand_kw']:.1f}",
            f"{record['hydro_kw']:.1f}",
            f"{record['battery_kw']:.1f}",
            f"{record['generator_kw']:.1f}",
            f"{record['spilled_kw']:.1f}",
            f"{record['unserved_kw']:.1f}",
            f"{record['battery_soc']*100:.1f}",
        ]

        for col, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(value)
            self.table.setItem(row, col, item)

        # Scroll to the latest row
        self.table.scrollToBottom()

    def reset(self):
        self.table.setRowCount(0)


class EMSSWindow (QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EMSS Hydroelectric Resort Simulator")

        # Init DB
        init_db()

        #Simulation
        self.config = SimulationConfig()
        self.sim = EMSSSimulator(self.config)

        #tabs
        self.hydro_tab = HydroTab()
        self.resort_tab = ResortTab()
        self.telemetry_tab = TelemetryTab()

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.hydro_tab, "Hydro Plant")
        self.tabs.addTab(self.resort_tab, "Resort")
        self.tabs.addTab(self.telemetry_tab, "Telemetry")

        #control button
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
        main_layout.addWidget(self.tabs)
        main_layout.addLayout(button_layout)
        
        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Time driven simulation
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.tick)

    def start_sim(self):
        self.timer.start()
    
    def stop_sim(self):
        self.timer.stop()
    
    def reset_sim(self):
        self.timer.stop()
        self.sim.reset()

        self.hydro_tab.reset()
        self.resort_tab.reset()
        self.telemetry_tab.reset()
    
    def tick(self):
        record = self.sim.step_once()

        self.hydro_tab.update_with_record(record)
        self.resort_tab.update_with_record(record)
        self.telemetry_tab.update_with_record(record)