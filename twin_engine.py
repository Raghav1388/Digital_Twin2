"""
twin_engine.py — PACKTWIN simulation core.

Pure Python, no GUI dependencies. This is the same physics model used in the
browser version: an OCV lookup table, a lumped thermal model, Coulomb counting
for SoC, and simple cell-imbalance / fault-injection logic.

Kept separate from the GUI so it can be tested or reused (e.g. in a headless
batch-analysis script) independent of PySide6.
"""

import csv
import io
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# ---------------------------------------------------------------- OCV model
OCV_TABLE = [
    (0, 3.00), (5, 3.30), (10, 3.45), (20, 3.60), (30, 3.68), (40, 3.72),
    (50, 3.75), (60, 3.78), (70, 3.82), (80, 3.89), (90, 4.02), (95, 4.10), (100, 4.20)
]


def ocv_from_soc(soc: float) -> float:
    soc = max(0.0, min(100.0, soc))
    for (s0, v0), (s1, v1) in zip(OCV_TABLE, OCV_TABLE[1:]):
        if s0 <= soc <= s1:
            f = (soc - s0) / (s1 - s0)
            return v0 + f * (v1 - v0)
    return OCV_TABLE[-1][1]


# ---------------------------------------------------------------- CSV ingest
@dataclass
class RealLog:
    time: List[float] = field(default_factory=list)      # minutes
    soc: List[float] = field(default_factory=list)        # %
    pack_v: List[float] = field(default_factory=list)     # V
    current: List[float] = field(default_factory=list)    # A
    temp: List[float] = field(default_factory=list)       # degC
    cell_v: List[List[float]] = field(default_factory=list)  # per-row list of per-cell V


def _detect_columns(fieldnames: List[str]):
    def find(pattern):
        for f in fieldnames:
            if re.search(pattern, f, re.IGNORECASE):
                return f
        return None

    def find_all(pattern):
        matches = [f for f in fieldnames if re.search(pattern, f, re.IGNORECASE)]
        def key(f):
            m = re.search(r'\d+', f)
            return int(m.group()) if m else 0
        return sorted(matches, key=key)

    return {
        'time': find(r'^time|timestamp|date'),
        'pack_v': find(r'pack.*volt|^voltage$|^packv'),
        'current': find(r'(?<![a-zA-Z])(current|amps?)(?![a-zA-Z])|^i$'),
        'soc': find(r'soc|state.*charge'),
        'temps': find_all(r'temp|therm'),
        'cells': find_all(r'cell.?\d+'),
    }


def parse_csv_text(text: str, nominal_ah: float, cell_count: int, sample_interval_min: float = 1.0) -> RealLog:
    """Parse a BMS CSV log into a RealLog, auto-detecting columns the same way
    the browser version does. Falls back to sensible defaults when columns
    (timestamp, per-cell voltages, SoC) are missing."""
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    cols = _detect_columns(fieldnames)

    rows = list(reader)
    real = RealLog()
    t0 = None
    soc_prev = 100.0

    for i, row in enumerate(rows):
        # --- time ---
        t_min = i * sample_interval_min
        if cols['time'] and row.get(cols['time']):
            try:
                d = datetime.fromisoformat(row[cols['time']].replace('Z', '+00:00'))
                if t0 is None:
                    t0 = d
                t_min = (d - t0).total_seconds() / 60.0
            except Exception:
                pass
        real.time.append(t_min)

        # --- cell voltages ---
        cv = []
        for c in cols['cells']:
            try:
                cv.append(float(row[c]))
            except (TypeError, ValueError, KeyError):
                pass
        if not cv and cols['pack_v'] and row.get(cols['pack_v']):
            try:
                base = float(row[cols['pack_v']]) / cell_count
                cv = [base + random.uniform(-0.005, 0.005) for _ in range(cell_count)]
            except ValueError:
                pass
        real.cell_v.append(cv)

        # --- pack voltage ---
        pv = None
        if cols['pack_v'] and row.get(cols['pack_v']):
            try:
                pv = float(row[cols['pack_v']])
            except ValueError:
                pass
        if pv is None and cv:
            pv = sum(cv)
        real.pack_v.append(pv if pv is not None else 0.0)

        # --- current ---
        cur = 0.0
        if cols['current'] and row.get(cols['current']):
            try:
                cur = float(row[cols['current']])
            except ValueError:
                pass
        real.current.append(cur)

        # --- temperature (average of detected temp columns) ---
        temps = []
        for tcol in cols['temps']:
            try:
                temps.append(float(row[tcol]))
            except (TypeError, ValueError, KeyError):
                pass
        real.temp.append(sum(temps) / len(temps) if temps else 25.0)

        # --- SoC ---
        if cols['soc'] and row.get(cols['soc']):
            try:
                soc_prev = float(row[cols['soc']])
            except ValueError:
                pass
        else:
            if i > 0:
                dt_h = (real.time[i] - real.time[i - 1]) / 60.0
                soc_prev = max(0.0, soc_prev - (cur * dt_h / nominal_ah * 100.0))
        real.soc.append(soc_prev)

    return real, cols


def generate_sample_csv(cell_count: int = 13, nominal_ah: float = 10.0) -> str:
    """Same synthetic discharge log the web version generates, for quick demos."""
    random.seed(7)
    rows = [['Timestamp', 'PackVoltage', 'Current', 'Temp1', 'Temp2', 'SOC'] +
            [f'Cell{i}' for i in range(1, cell_count + 1)]]
    soc, temp = 92.0, 26.0
    t0 = datetime(2026, 8, 10, 9, 0, 0)
    offsets = [random.uniform(-0.008, 0.008) for _ in range(cell_count)]
    if cell_count >= 7:
        offsets[6] -= 0.035  # mildly weak cell, same as the reference sample
    rint = 0.035

    out_rows = []
    for m in range(45):
        current = 3.0 + 0.4 * math.sin(m / 7) + random.uniform(-0.15, 0.15)
        if 20 <= m <= 22:
            current += 2.0
        dt_h = 1 / 60
        soc = max(0.0, soc - (current * dt_h) / nominal_ah * 100.0)
        qgen = current * current * (rint * cell_count)
        temp += (qgen - (temp - 25) / 1.5) / 900 * 60
        temp = max(24.0, temp)
        v_ocv = ocv_from_soc(soc)
        cells = [v_ocv + offsets[i] - current * rint for i in range(cell_count)]
        packv = sum(cells)
        ts = (t0.replace(minute=(t0.minute + m) % 60,
                          hour=t0.hour + (t0.minute + m) // 60)).isoformat()
        out_rows.append([ts, f'{packv:.3f}', f'{current:.2f}', f'{temp:.1f}', f'{temp - 0.5:.1f}',
                          f'{soc:.2f}'] + [f'{c:.3f}' for c in cells])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rows[0])
    w.writerows(out_rows)
    return buf.getvalue()


# ---------------------------------------------------------------- Simulation
@dataclass
class SimParams:
    nominal_ah: float = 10.0
    cell_count: int = 13
    r_int_ohm: float = 0.035        # per cell
    ambient_c: float = 25.0
    pattern: str = 'discharge'      # discharge | charge | fastcharge | pulse
    c_rate: float = 0.5
    duration_min: int = 60
    cycles: int = 0
    balancing_on: bool = True
    fault_weak_cell: bool = False
    weak_cell_idx: int = 0
    fault_sensor: bool = False
    fault_spike: bool = False


@dataclass
class SimResult:
    time: List[float] = field(default_factory=list)
    soc: List[float] = field(default_factory=list)
    pack_v: List[float] = field(default_factory=list)
    temp: List[float] = field(default_factory=list)
    temp_sensor: List[float] = field(default_factory=list)
    min_cell: List[float] = field(default_factory=list)
    max_cell: List[float] = field(default_factory=list)
    avg_cell: List[float] = field(default_factory=list)
    cell_v: List[List[float]] = field(default_factory=list)
    effective_ah: float = 10.0
    nominal_ah: float = 10.0
    fault_log: List[dict] = field(default_factory=list)


def _current_profile(pattern: str, crate_amp: float, t_min: float) -> float:
    if pattern == 'discharge':
        return crate_amp
    if pattern in ('charge', 'fastcharge'):
        return -crate_amp
    if pattern == 'pulse':
        cyc = t_min % 4
        return crate_amp * 1.6 if cyc < 2 else crate_amp * 0.3
    return crate_amp


def run_simulation(params: SimParams, real: Optional[RealLog] = None) -> SimResult:
    fault_log = []
    effective_ah = max(params.nominal_ah * 0.5, params.nominal_ah * (1 - 0.00025 * params.cycles))
    if params.cycles > 0:
        fault_log.append({
            't': 0, 'alert': effective_ah / params.nominal_ah < 0.8,
            'msg': f"Virtual aging: {params.cycles} cycles fast-forwarded -> capacity derated to "
                   f"{effective_ah:.2f}Ah ({effective_ah/params.nominal_ah*100:.1f}% SoH)"
        })

    cell_count = params.cell_count
    if real and real.time:
        t0 = real.time[-1]
        soc = real.soc[-1]
        temp = real.temp[-1]
        cv_last = real.cell_v[-1] if real.cell_v and real.cell_v[-1] else None
        if cv_last:
            mean = sum(cv_last) / len(cv_last)
            offsets = [(cv_last[i] - mean) if i < len(cv_last) else random.uniform(-0.0075, 0.0075)
                       for i in range(cell_count)]
        else:
            offsets = [random.uniform(-0.0075, 0.0075) for _ in range(cell_count)]
    else:
        t0, soc, temp = 0.0, 90.0, params.ambient_c
        offsets = [random.uniform(-0.0075, 0.0075) for _ in range(cell_count)]

    if params.fault_weak_cell:
        offsets[params.weak_cell_idx] -= 0.10
        fault_log.append({'t': t0, 'alert': True,
                           'msg': f"Weak cell fault active on cell #{params.weak_cell_idx+1} "
                                  f"(-100mV offset, 2.5x resistance)"})

    spike_start = params.duration_min * 0.4 + random.random() * params.duration_min * 0.2
    spike_logged = False
    sensor_frozen = None
    tripped = False

    crate_amp = params.c_rate * params.nominal_ah
    dt = 1.0
    Rth, Cth = 1.5, 900.0  # °C/W, J/°C — tuned for a small naturally-cooled 10Ah pack
    res = SimResult(effective_ah=effective_ah, nominal_ah=params.nominal_ah)

    t = 0.0
    while t <= params.duration_min:
        I = _current_profile(params.pattern, crate_amp, t)
        if params.fault_spike and spike_start <= t < spike_start + 3:
            I *= 2.5
            if not spike_logged:
                fault_log.append({'t': t0 + t, 'alert': True,
                                   'msg': f"Over-current spike triggered at t={t0+t:.0f}min ({I:.1f}A)"})
                spike_logged = True

        soc -= (I * dt / 60) / effective_ah * 100
        soc = max(0.0, min(100.0, soc))

        pack_r = params.r_int_ohm * cell_count
        qgen = I * I * pack_r
        d_temp = ((qgen - (temp - params.ambient_c) / Rth) / Cth) * (dt * 60)
        temp += d_temp
        temp = max(params.ambient_c - 2, min(90.0, temp))

        if params.fault_sensor:
            if sensor_frozen is None:
                sensor_frozen = temp
            sensor_reading = sensor_frozen
        else:
            sensor_reading = temp

        if params.balancing_on:
            min_off = min(offsets)
            for i in range(cell_count):
                if offsets[i] > min_off + 0.003:
                    offsets[i] -= 0.0006

        ocv = ocv_from_soc(soc)
        cells = []
        for i in range(cell_count):
            local_r = params.r_int_ohm * 2.5 if (params.fault_weak_cell and i == params.weak_cell_idx) else params.r_int_ohm
            v = ocv + offsets[i] - I * local_r
            cells.append(v)
            if (v < 2.8 or v > 4.25) and not tripped:
                tripped = True
                fault_log.append({'t': t0 + t, 'alert': True,
                                   'msg': f"Protection trip: cell #{i+1} reached {v:.2f}V at t={t0+t:.0f}min"})

        res.time.append(t0 + t)
        res.soc.append(soc)
        res.pack_v.append(sum(cells))
        res.temp.append(temp)
        res.temp_sensor.append(sensor_reading)
        res.min_cell.append(min(cells))
        res.max_cell.append(max(cells))
        res.avg_cell.append(sum(cells) / len(cells))
        res.cell_v.append(cells)

        if tripped:
            break
        t += dt

    res.fault_log = fault_log
    return res


def usability_verdict(res: SimResult):
    soh = res.effective_ah / res.nominal_ah * 100
    peak_temp = max(res.temp) if res.temp else 0.0
    imbalances = [max(c) - min(c) for c in res.cell_v] if res.cell_v else [0.0]
    max_imbalance_mv = max(imbalances) * 1000
    tripped = any('Protection trip' in f['msg'] for f in res.fault_log)

    level, label = 'good', 'Good — fit for continued use'
    if tripped or soh < 70 or peak_temp > 55 or max_imbalance_mv > 150:
        level, label = 'poor', 'Poor — service required before further use'
    elif soh < 85 or peak_temp > 45 or max_imbalance_mv > 80:
        level, label = 'marginal', 'Marginal — monitor closely, plan maintenance'

    return {
        'level': level, 'label': label, 'soh': soh, 'peak_temp': peak_temp,
        'max_imbalance_mv': max_imbalance_mv, 'tripped': tripped
    }
