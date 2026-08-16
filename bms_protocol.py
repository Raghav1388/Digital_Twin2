"""
bms_protocol.py — Sara Controls & Automation smart-BMS UART protocol.

This is a direct Python port of the protocol already proven working in the
"Li-Ion Battery Data Logging Software" web tool: standard lithium BMS UART
framing (start 0xA5, host address 0x40, cmd, length 0x08, 8 data bytes,
checksum = sum-of-bytes & 0xFF), commands 0x90-0x98.

Read-only: this module never sends MOS on/off or configuration write commands.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

CMDS = [0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98]

FAULT_BITS = [
    'CELL_OV_L1', 'CELL_OV_L2', 'CELL_UV_L1', 'CELL_UV_L2', 'PACK_OV_L1', 'PACK_OV_L2', 'PACK_UV_L1', 'PACK_UV_L2',
    'CHG_OVER_TEMP_L1', 'CHG_OVER_TEMP_L2', 'CHG_UNDER_TEMP_L1', 'CHG_UNDER_TEMP_L2', 'DSG_OVER_TEMP_L1',
    'DSG_OVER_TEMP_L2', 'DSG_UNDER_TEMP_L1', 'DSG_UNDER_TEMP_L2',
    'CHG_OVERCURRENT_L1', 'CHG_OVERCURRENT_L2', 'DSG_OVERCURRENT_L1', 'DSG_OVERCURRENT_L2', 'SOC_HIGH_L1',
    'SOC_HIGH_L2', 'SOC_LOW_L1', 'SOC_LOW_L2',
    'CELL_DIFF_L1', 'CELL_DIFF_L2', 'MODULE_OVER_TEMP_L1', 'MODULE_OVER_TEMP_L2', 'MODULE_UNDER_TEMP_L1',
    'MODULE_UNDER_TEMP_L2', 'MODULE_TEMP_DIFF_L1', 'MODULE_TEMP_DIFF_L2',
    'CHG_MOS_OVER_TEMP', 'DSG_MOS_OVER_TEMP', 'CHG_MOS_TEMP_SENSOR_FAIL', 'DSG_MOS_TEMP_SENSOR_FAIL',
    'CHG_MOS_ADHESION', 'DSG_MOS_ADHESION', 'CHG_MOS_BREAKER_FAIL', 'DSG_MOS_BREAKER_FAIL',
    'AFE_COLLECT_FAIL', 'VOLTAGE_COLLECT_DROP', 'CELL_TEMP_SENSOR_FAIL', 'EEPROM_FAIL', 'RTC_FAIL',
    'PRECHARGE_FAIL', 'COMMS_FAIL', 'NETWORK_COMMS_FAIL'
]


@dataclass
class BMSState:
    volt: Optional[float] = None
    current: Optional[float] = None
    soc: Optional[float] = None
    max_cell_mv: Optional[int] = None
    min_cell_mv: Optional[int] = None
    max_cell_no: Optional[int] = None
    min_cell_no: Optional[int] = None
    max_temp: Optional[int] = None
    min_temp: Optional[int] = None
    charge_mos: Optional[bool] = None
    discharge_mos: Optional[bool] = None
    residual_ah: Optional[float] = None
    cells: List[Optional[float]] = field(default_factory=lambda: [None] * 32)  # mV
    cell_temps: List[Optional[float]] = field(default_factory=lambda: [None] * 32)
    reported_cell_count: Optional[int] = None
    temp_sensor_count: Optional[int] = None
    charger_status: Optional[bool] = None
    load_status: Optional[bool] = None
    cycles: Optional[int] = None
    balance_states: List[bool] = field(default_factory=list)
    faults: List[str] = field(default_factory=list)

    def cell_list(self) -> List[float]:
        """Cell voltages actually reported so far, in volts."""
        return [v / 1000.0 for v in self.cells if v is not None]


def build_request(cmd: int) -> bytes:
    """13-byte poll frame: A5 40 <cmd> 08 00*8 <checksum>"""
    f = bytearray(13)
    f[0] = 0xA5
    f[1] = 0x40
    f[2] = cmd
    f[3] = 0x08
    checksum = sum(f[:12]) & 0xFF
    f[12] = checksum
    return bytes(f)


def drain_frames(buf: bytearray) -> Tuple[List[bytes], bytearray]:
    """Pull any complete, checksum-valid 13-byte frames out of a growing
    receive buffer. Mirrors the web version's drainFrames() exactly."""
    frames = []
    while True:
        try:
            start_idx = buf.index(0xA5)
        except ValueError:
            buf.clear()
            return frames, buf
        if start_idx > 0:
            del buf[:start_idx]
        if len(buf) < 13:
            return frames, buf
        frame = bytes(buf[:13])
        checksum = sum(frame[:12]) & 0xFF
        if checksum != frame[12]:
            del buf[0]
            continue
        frames.append(frame)
        del buf[:13]


def handle_frame(state: BMSState, frame: bytes) -> int:
    """Apply one decoded frame to state in place. Returns the command byte."""
    cmd = frame[2]
    d = frame[4:12]

    if cmd == 0x90:
        state.volt = ((d[0] << 8) | d[1]) / 10.0
        state.current = (((d[4] << 8) | d[5]) - 30000) / 10.0
        state.soc = ((d[6] << 8) | d[7]) / 10.0
    elif cmd == 0x91:
        state.max_cell_mv = (d[0] << 8) | d[1]
        state.max_cell_no = d[2]
        state.min_cell_mv = (d[3] << 8) | d[4]
        state.min_cell_no = d[5]
    elif cmd == 0x92:
        state.max_temp = d[0] - 40
        state.min_temp = d[2] - 40
    elif cmd == 0x93:
        state.charge_mos = d[1] == 1
        state.discharge_mos = d[2] == 1
        state.residual_ah = ((d[4] << 24) | (d[5] << 16) | (d[6] << 8) | d[7]) / 1000.0
    elif cmd == 0x94:
        state.reported_cell_count = d[0]
        state.temp_sensor_count = d[1]
        state.charger_status = d[2] == 1
        state.load_status = d[3] == 1
        state.cycles = (d[5] << 8) | d[6]
    elif cmd == 0x95:
        frame_no = d[0]
        vs = [(d[1] << 8) | d[2], (d[3] << 8) | d[4], (d[5] << 8) | d[6]]
        for i, mv in enumerate(vs):
            idx = (frame_no - 1) * 3 + i
            if mv > 0 and idx < len(state.cells):
                state.cells[idx] = mv
    elif cmd == 0x96:
        frame_no = d[0]
        for i in range(7):
            raw = d[i + 1]
            idx = (frame_no - 1) * 7 + i
            if raw > 0 and idx < len(state.cell_temps):
                state.cell_temps[idx] = raw - 40
    elif cmd == 0x97:
        bits = []
        for byte_idx in range(6):
            for bit in range(8):
                bits.append(((d[byte_idx] >> bit) & 1) == 1)
        state.balance_states = bits
    elif cmd == 0x98:
        active = []
        for byte_idx in range(6):
            for bit in range(8):
                flag_idx = byte_idx * 8 + bit
                if ((d[byte_idx] >> bit) & 1) == 1 and flag_idx < len(FAULT_BITS):
                    active.append(FAULT_BITS[flag_idx])
        state.faults = active

    return cmd
