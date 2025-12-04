# domain/simulation.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict


@dataclass
class SimulationConfig:
    time_step_minutes: int = 15
    num_days: int = 7


class EMSSSimulator:
    """
    Minimal simulator stub.
    We'll fill in real hydro/battery/generator logic later.
    """

    def __init__(self, config: SimulationConfig | None = None):
        self.config = config or SimulationConfig()
        self.time_step_hours = self.config.time_step_minutes / 60
        self.reset()

    def reset(self):
        self.step = 0
        self.current_time = datetime.now()
        self.battery_soc = 0.5
        self.reservoir_level_m3 = 50_000.0

    def step_once(self) -> Dict:
        """
        Advance simulation by one time step and return a dummy record.
        Later this will include demand_kw, hydro_kw, etc.
        """
        record = {
            "step": self.step,
            "time": self.current_time,
            "demand_kw": 100.0,
            "hydro_kw": 80.0,
            "battery_kw": 10.0,
            "generator_kw": 10.0,
            "spilled_kw": 0.0,
            "unserved_kw": 0.0,
            "battery_soc": self.battery_soc,
            "reservoir_level_m3": self.reservoir_level_m3,
        }

        # advance fake state
        self.step += 1
        self.current_time += timedelta(minutes=self.config.time_step_minutes)

        return record
