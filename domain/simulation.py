# domain/simulation.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict
import math
import random


@dataclass
class SimulationConfig:
    # Time settings
    time_step_minutes: int = 15
    num_days: int = 7

    #Hydroelectric Plant
    max_turbine_kw: float = 500.0 # Max Electrical Output From The Turbine
    max_reservoir_m3: float = 100_000.0 # Full Reservoir
    min_reservoir_m3: float = 5_000.0 # below this, can't run at full power

    # Reservoir inflow 
    base_inflow_m3_per_hour: float = 150.0

    # Battery
    battery_capacity_kwh: float = 1_000.0
    max_charge_kw: float = 200.0
    max_discharge_kw: float = 200.0
    round_trip_efficiency: float = 0.9

    # Generator
    max_generator_kw: float = 400.0
    fuel_cost_per_kwh: float = 0.2

    # Resort layout
    num_standard_rooms: int = 20
    num_suite_rooms: int = 5

    #kwh per occupied room
    standard_room_kw_per_room: float = 2.5
    suite_room_kw_per_room: float = 4.0

    # Shared area capacities and load
    restaurant_base_kw: float = 20.0
    restaurant_kw_per_customer: float = 0.5

    spa_base_kw: float = 10.0
    spa_kw_per_customer: float = 0.7

    lobby_base_kw: float = 8.0
    lobby_kw_per_customer: float = 0.2

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
        """Reset simulation state to initial conditions."""
        self.step = 0
        self.current_time = datetime.now()

        # Start with half-full reservoir and battery
        self.reservoir_level_m3 = self.config.max_reservoir_m3 * 0.5
        self.battery_soc = 0.5 # 0–1 (fraction of capacity)

        # Resort state
        self.standard_rooms_occupied = 0
        self.suite_rooms_occupied = 0
        self.restaurant_customers = 0
        self.spa_customers = 0
        self.lobby_customers = 0

    def step_once(self) -> Dict:
        # 1) Update resort & get demand
        resort_state = self._resort_step()
        demand_kw = resort_state["total_demand_kw"]

        # 2) Reservoir inflow
        inflow_m3 = self._inflow_m3_per_step()
        self.reservoir_level_m3 = min(
            self.config.max_reservoir_m3,
            self.reservoir_level_m3 + inflow_m3,
        )

        # 3) Max hydro power
        max_hydro_kw = self._hydro_power_kw()

        # 4) Dispatch
        dispatch = self._dispatch(
            demand_kw=demand_kw,
            max_hydro_kw=max_hydro_kw,
        )

        # 5) Battery, reservoir updates
        self._update_battery_soc(dispatch["battery_kw"])
        self._update_reservoir(dispatch["hydro_kw"])

        # 6) Build record
        record = {
            "step": self.step,
            "time": self.current_time,
            "demand_kw": demand_kw,
            "hydro_kw": dispatch["hydro_kw"],
            "battery_kw": dispatch["battery_kw"],
            "generator_kw": dispatch["generator_kw"],
            "spilled_kw": dispatch["spilled_kw"],
            "unserved_kw": dispatch["unserved_kw"],
            "battery_soc": self.battery_soc,
            "reservoir_level_m3": self.reservoir_level_m3,
            # NEW: detailed resort state
            "resort": resort_state,
        }

        self.step += 1
        self.current_time += timedelta(minutes=self.config.time_step_minutes)

        return record

    
    # -------- Demand Model -----------

    def _resort_step(self) -> Dict:
        """
        Update resort occupancy and compute total electric demand.

        We simulate:
          - Room bookings (standard + suites)
          - Customers visiting restaurant, spa, lobby

        This is a simplified aggregate model (counts, not individual guests).
        """
        
        cfg = self.config

        # Determine time-of-day (0–24)
        minutes_in_day = 24 * 60
        minutes_since_start_of_day = (self.step * cfg.time_step_minutes) % minutes_in_day
        hour = minutes_since_start_of_day / 60.0

        # ----- Room occupancy: bookings/checkouts -----

        # Target occupancy ratios by time of day (guests stay overnight, slow turnover)
        # Example: high occupancy at night, bit lower midday.
        if 0 <= hour < 6:
            target_occ = 0.8
        elif 6 <= hour < 12:
            target_occ = 0.7
        elif 12 <= hour < 18:
            target_occ = 0.6
        elif 18 <= hour < 22:
            target_occ = 0.9
        else:
            target_occ = 0.85

        # Smoothly move current occupancy towards target
        total_rooms = cfg.num_standard_rooms + cfg.num_suite_rooms
        current_rooms_occupied = self.standard_rooms_occupied + self.suite_rooms_occupied
        target_rooms_occupied = int(total_rooms * target_occ)

        # Adjust a little each step (simulating bookings/checkouts)
        max_change_per_step = max(1, total_rooms // 20)  # don't jump too fast
        delta = target_rooms_occupied - current_rooms_occupied
        if abs(delta) > max_change_per_step:
            delta = max_change_per_step if delta > 0 else -max_change_per_step

        new_total_rooms_occupied = max(0, min(total_rooms, current_rooms_occupied + delta))

        # Split between standard and suites (e.g., 80/20 split)
        if new_total_rooms_occupied > 0:
            suite_target = int(new_total_rooms_occupied * 0.2)
            suite_target = min(suite_target, cfg.num_suite_rooms)
            standard_target = new_total_rooms_occupied - suite_target
            standard_target = min(standard_target, cfg.num_standard_rooms)
        else:
            standard_target = 0
            suite_target = 0

        self.standard_rooms_occupied = standard_target
        self.suite_rooms_occupied = suite_target

        # ----- Shared areas occupancy: where are people right now? -----

        total_guests = self.standard_rooms_occupied * 2 + self.suite_rooms_occupied * 3  # assume avg guests per room

        # Simple time-of-day behavior:
        # - Breakfast in restaurant (7–10)
        # - Spa in afternoon (14–18)
        # - Restaurant again in evening (18–22)
        # - Lobby always has some people
        restaurant_frac = 0.0
        spa_frac = 0.0

        if 7 <= hour <= 10:
            restaurant_frac = 0.4
        elif 18 <= hour <= 22:
            restaurant_frac = 0.5

        if 14 <= hour <= 18:
            spa_frac = 0.25

        # Lobby: small fraction always moving through
        lobby_frac = 0.1

        # Cap fractions so they don't exceed 1 total
        total_frac = restaurant_frac + spa_frac + lobby_frac
        if total_frac > 0.8:
            scale = 0.8 / total_frac
            restaurant_frac *= scale
            spa_frac *= scale
            lobby_frac *= scale

        self.restaurant_customers = int(total_guests * restaurant_frac)
        self.spa_customers = int(total_guests * spa_frac)
        self.lobby_customers = int(total_guests * lobby_frac)

        # ----- Compute electric demand from all areas -----

        # Rooms
        room_kw = (
            self.standard_rooms_occupied * cfg.standard_room_kw_per_room
            + self.suite_rooms_occupied * cfg.suite_room_kw_per_room
        )

        # Shared areas
        restaurant_kw = (
            cfg.restaurant_base_kw
            + self.restaurant_customers * cfg.restaurant_kw_per_customer
        )
        spa_kw = cfg.spa_base_kw + self.spa_customers * cfg.spa_kw_per_customer
        lobby_kw = cfg.lobby_base_kw + self.lobby_customers * cfg.lobby_kw_per_customer

        total_demand_kw = room_kw + restaurant_kw + spa_kw + lobby_kw

        return {
            "total_demand_kw": total_demand_kw,
            "room_kw": room_kw,
            "restaurant_kw": restaurant_kw,
            "spa_kw": spa_kw,
            "lobby_kw": lobby_kw,
            "standard_rooms_occupied": self.standard_rooms_occupied,
            "suite_rooms_occupied": self.suite_rooms_occupied,
            "restaurant_customers": self.restaurant_customers,
            "spa_customers": self.spa_customers,
            "lobby_customers": self.lobby_customers,
            "total_guests": total_guests,
            "hour": hour,
        }

    
    @staticmethod
    def _smooth_bump(hour: float, start: float, end: float) -> float:
        """
        Return a smooth bump (0 to 1) between start and end hours using a cosine.
        Outside [start, end], returns 0.
        """
        if hour < start or hour < end:
            return 0.0
        # normalise to 0..pi
        x = (hour - start) / (end - start) * math.pi
        # cosine bump: 0 at edges, 1 at center
        return 0.5 * (1 - math.cos(x))
    
    # ---------- Hydroelectric & reservoir ----------
    def _inflow_m3_per_step(self) -> float:
        """
        Simple inflow model:
          - constant base inflow
          - small daily variation (e.g., snowmelt/temperature pattern)
        """

        # base hourly inflow
        base = self.config.base_inflow_m3_per_hour

        # Add a small sinusoidal variation over the day
        minutes_per_day = 24 * 60
        minutes = (self.step * self.config.time_step_minutes) & minutes_per_day
        hour = minutes / 60.0
        daily_factor = 1.0 + 0.2 * math.sin(2 * math.pi * (hour / 24.0))

        inflow_per_hour = base * daily_factor
        inflow_per_step = inflow_per_hour * self.time_step_hours
        return inflow_per_step
    
    def _hydro_power_kw(self) -> float:
        """
        Approximate available hydro power based on reservoir fullness.
        - If reservoir is low, you can't run at full turbine rating.
        - If it's above a threshold, you can use full rating.
        """

        # Fraction of reservoir between min and max
        level = self.reservoir_level_m3
        cfg = self.config

        if level <= cfg.min_reservoir_m3:
            return 0.0
        
        # Scale between min_reservoir_m3 and max_reservoir_m3
        fullness = (level - cfg.min_reservoir_m3) / (cfg.max_reservoir_m3 - cfg.min_reservoir_m3)
        fullness = max(0.0, min(fullness, 1.0))

        return fullness * cfg.max_turbine_kw
    
    def _update_reservoir(self, hydro_kw: float):
        """
        Reduce reservoir level based on hydro energy produced this step.
        We assume a simple constant ratio of water volume per kWh.
        """

        water_per_kwh_m3 = 0.1 # tunable constant: m3 of water per kWh
        energy_kwh = hydro_kw * self.time_step_hours
        water_used_m3 = energy_kwh * water_per_kwh_m3

        self.reservoir_level_m3 = max(0.0, self.reservoir_level_m3 - water_used_m3)


    # -------- Battery ----------

    def _update_battery_soc(self, battery_kw: float):
        """
        Update battery SoC based on net battery power:
          - positive battery_kw  = discharging (supplying load)
          - negative battery_kw = charging
        """
        cfg = self.config

        # Convert current SoC to energy
        current_kwh = self.battery_soc * cfg.battery_capacity_kwh

        # Energy change this step BEFORE effciency (kWh)
        delta_kwh = battery_kw * self.time_step_hours

        if delta_kwh > 0:
            # discharging: we lose some energy in the process
            # Simplify: actual stored energy removed = delta_kwh / efficiency
            efficient_delta = delta_kwh / cfg.round_trip_efficiency
            current_kwh = max(0.0, current_kwh - efficient_delta)
        elif delta_kwh < 0:
            # charging: not all power goes into storage
            efficient_delta = delta_kwh * cfg.round_trip_efficiency
            current_kwh = min(cfg.battery_capacity_kwh, current_kwh - efficient_delta)

        # Recompute Soc
        self.battery_soc = max(0.0, min(1.0, current_kwh / cfg.battery_capacity_kwh))

    
    # ----------- Dispatch Logic -------------

    def _dispatch(self, demand_kw: float, max_hydro_kw: float) -> Dict:
        """
        Decide how to meet demand using:
          1. Hydro (up to max_hydro_kw)
          2. Battery
          3. Generator

        Returns dict with:
          hydro_kw, battery_kw, generator_kw, spilled_kw, unserved_kw
        """
        cfg = self.config

        remaining = demand_kw

        # 1) Use Hydro to meet demand
        hydro_kw = min(max_hydro_kw, remaining)
        remaining -= hydro_kw

        battery_kw = 0.0
        generator_kw = 0.0
        spilled_kw = 0.0

        # If there is unused hydro capacity, try to charge battery
        surplus_hydro_kw = max(0.0, max_hydro_kw - hydro_kw)
        if surplus_hydro_kw > 0:
            battery_kw, spill_from_surplus = self._charge_battery_with_surplus(surplus_hydro_kw)
            spilled_kw += spill_from_surplus

        # 2) Discharge battery if still demand
        if remaining > 0:
            used_from_battery = self._discharge_battery_to_meet_load(remaining)
            battery_kw += used_from_battery
            remaining -= used_from_battery

        # 3) Use generator if still demand left
        if remaining > 0:
            generator_kw = min(cfg.max_generator_kw, remaining)
            remaining -= generator_kw

        unserved_kw = max(0.0, remaining)

        return {
            "hydro_kw": hydro_kw,
            "battery_kw": battery_kw,
            "generator_kw": generator_kw,
            "spilled_kw": spilled_kw,
            "unserved_kw": unserved_kw
        }
    
    def _charge_battery_with_surplus(self, surplus_hydro_kw: float) -> tuple[float, float]:
        """
        Use surplus hydro to charge the battery.
        Returns (battery_kw, spilled_kw_from_surplus).

        battery_kw is negative (charging).
        """
        cfg = self.config


        # current stored energy
        current_kwh = self.battery_soc * cfg.battery_capacity_kwh
        free_space_kwh = cfg.battery_capacity_kwh - current_kwh
        if free_space_kwh <= 0:
            # battery full, spill everything
            return 0.0, surplus_hydro_kw
        
        # Max we can push in this step due to power limit
        max_charge_this_step_kwh = cfg.max_charge_kw * self.time_step_hours

        # Energy available from surplus hydro this step
        available_kwh = surplus_hydro_kw * self.time_step_hours

        # Energy that actually goes into the battery (kWh stored)
        charge_kwh_stored = min(free_space_kwh, max_charge_this_step_kwh, available_kwh * cfg.round_trip_efficiency)
        if charge_kwh_stored <= 0:
            return 0.0, surplus_hydro_kw
        
        # Corresponding power at the grid side (before efficiency losses)
        # available_kwh * eff = stored, so grid-side energy used = stored / eff
        grid_energy_used_kwh = charge_kwh_stored / cfg.round_trip_efficiency
        battery_kw = -grid_energy_used_kwh / self.time_step_hours # negative = charging

        # Water/hydro wise, we consumed grid_energy_used_kwh from surplus_hydro_kw.
        # Compute remaining surplus (if we didn't use all)
        used_surplus_kw = grid_energy_used_kwh / self.time_step_hours
        spilled_kw = max(0.0, surplus_hydro_kw - used_surplus_kw)

        # Update battery SoC here, or leave to _update_battery_soc?
        # We let _update_battery_soc() handle all SoC updates using net battery_kw.

        return battery_kw, spilled_kw
    
    def _discharge_battery_to_meet_load(self, remaining_kw: float) -> float:
        """
        Decide how much battery to discharge (kW) to meet remaining load,
        respecting power limits and available stored energy.

        Returns the battery discharge power (positive kW).
        """
        cfg = self.config

        current_kwh = self.battery_soc * cfg.battery_capacity_kwh
        if current_kwh <= 0:
            return 0.0
        
        max_discharge_this_step_kwh = cfg.max_discharge_kw * self.time_step_hours

        # We can't discharge more energy than we have
        possible_discharge_kwh = min(current_kwh, max_discharge_this_step_kwh)

        # We want energy = remaining_kw * dt, but limited by possible_discharge_kwh
        discharge_kwh = min(remaining_kw * self.time_step_hours, possible_discharge_kwh)
        if discharge_kwh <= 0:
            return 0.0
        
         # Power from battery = energy / dt
        discharge_kw = discharge_kwh / self.time_step_hours
        return discharge_kw
