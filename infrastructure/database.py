# infrastructure/database.py
import sqlite3
from pathlib import Path

DB_PATH = Path("emss.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT,
          started_at TEXT,
          num_days INTEGER,
          time_step_minutes INTEGER
        );

        CREATE TABLE IF NOT EXISTS telemetry (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER,
          ts TEXT,
          step INTEGER,
          demand_kw REAL,
          hydro_kw REAL,
          battery_kw REAL,
          generator_kw REAL,
          spilled_kw REAL,
          unserved_kw REAL,
          battery_soc REAL,
          reservoir_level_m3 REAL,
          FOREIGN KEY (run_id) REFERENCES runs(id)
        );
        """
    )
    conn.commit()
    conn.close()
