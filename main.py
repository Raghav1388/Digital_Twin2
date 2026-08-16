"""
Sara Controls & Automation — Li-Ion Battery Digital Twin
Native instrumentation-panel GUI (PySide6 + pyqtgraph), with a real, working
smart-BMS UART protocol decoder (ported from the company's own data-logging
tool) driving both the live readouts and the CSV recording pipeline that
feeds the twin simulation.

Run:  python main.py
"""
import sys
import io
import csv
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QSlider, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QScrollArea, QListWidget, QListWidgetItem,
    QPlainTextEdit, QFormLayout, QFrame
)

import pyqtgraph as pg
import twin_engine as te
import bms_protocol as bp

try:
    import serial
    import serial.tools.list_ports as list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

ASSETS_DIR = os.path.join(
    getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'assets'
)

# ----------------------------------------------------------------- Sara Controls & Automation palette
TEAL = '#1fb3ac'
TEAL_BRIGHT = '#4de0d6'
AMBER = '#eaa458'
VIOLET = '#a48cf2'
ROSE = '#ef7fa8'
GREEN = '#38d996'
RED = '#f2606b'
BG = '#0a0e13'
PANEL = '#101720'
CARD = '#141d27'
CARD2 = '#0e141c'
BORDER = '#1c2830'
TEXT = '#e7eef2'
TEXT_DIM = '#93a6b3'
TEXT_MUTE = '#5b6b78'

APP_QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Inter', 'Segoe UI', Arial; font-size: 12px; }}
QGroupBox {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {PANEL}, stop:1 {CARD2});
    border: 1px solid {BORDER}; border-radius: 14px;
    margin-top: 14px; padding: 14px 10px 10px 10px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {TEXT_MUTE};
    font-size: 10.5px; letter-spacing: 1px; text-transform: uppercase;
}}
QGroupBox#grpLoad {{ border-top: 3px solid {TEAL}; }}
QGroupBox#grpParams {{ border-top: 3px solid {VIOLET}; }}
QGroupBox#grpScenario {{ border-top: 3px solid {AMBER}; }}
QGroupBox#grpFault {{ border-top: 3px solid {ROSE}; }}
QGroupBox#grpSerial {{ border-top: 3px solid {TEAL_BRIGHT}; }}
QGroupBox#grpVerdict {{ border-top: 3px solid {GREEN}; }}
QGroupBox#grpLive {{ border-top: 3px solid {TEAL_BRIGHT}; }}
QPushButton {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 10px; font-weight: 600; color: {TEXT};
}}
QPushButton:hover {{ border-color: rgba(31,179,172,.5); }}
QPushButton:disabled {{ opacity: 0.4; color: {TEXT_MUTE}; }}
QPushButton#btnRun {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {TEAL}, stop:1 {TEAL_BRIGHT});
    color: #06201e; border: none; font-size: 13px; padding: 12px; font-weight: 700;
}}
QPushButton#btnPrimary {{ background: rgba(31,179,172,.14); color: {TEAL_BRIGHT}; border: 1px solid rgba(31,179,172,.35); }}
QPushButton#btnDanger {{ background: rgba(242,96,107,.10); color: {RED}; border: 1px solid rgba(242,96,107,.30); }}
QLabel#lblValue {{ font-family: 'Consolas','JetBrains Mono',monospace; font-weight: 700; font-size: 15px; }}
QLabel#lblCaption {{ color: {TEXT_MUTE}; font-size: 9.5px; letter-spacing: 1px; }}
QSlider::groove:horizontal {{ height: 8px; border-radius: 4px; background: {BORDER}; }}
QSlider::handle:horizontal {{
    background: {TEAL_BRIGHT}; border: 2px solid {BG}; width: 16px; height: 16px;
    margin: -5px 0; border-radius: 8px;
}}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 6px; color: {TEXT};
}}
QCheckBox {{ font-weight: 500; }}
QPlainTextEdit {{
    background: #050807; color: #6ee7b7; border-radius: 8px; font-family: Consolas, monospace; font-size: 10.5px;
    border: 1px solid {BORDER};
}}
QListWidget {{ border: none; background: transparent; font-family: Consolas, monospace; font-size: 10.5px; }}
"""

SCROLLBAR_QSS = f"""
QScrollArea {{ border: none; }}
QScrollBar:vertical {{
    background: {BG}; width: 16px; margin: 2px; border-radius: 8px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; min-height: 32px; border-radius: 7px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEAL}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background: {BG}; height: 14px; margin: 2px; border-radius: 7px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER}; min-width: 32px; border-radius: 6px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TEAL}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""

SLIDER_GRADIENTS = {
    'ambTemp': f"QSlider::groove:horizontal {{ height:8px; border-radius:4px; background: "
                f"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {RED}, stop:0.16 {AMBER}, stop:0.34 {GREEN}, "
                f"stop:0.66 {GREEN}, stop:0.84 {AMBER}, stop:1 {RED}); }} "
                f"QSlider::handle:horizontal {{ background:{RED}; border:2px solid {BG}; width:16px; height:16px; margin:-5px 0; border-radius:8px; }}",
    'crate': f"QSlider::groove:horizontal {{ height:8px; border-radius:4px; background: "
             f"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {GREEN}, stop:0.42 {GREEN}, stop:0.68 {AMBER}, stop:1 {RED}); }} "
             f"QSlider::handle:horizontal {{ background:{GREEN}; border:2px solid {BG}; width:16px; height:16px; margin:-5px 0; border-radius:8px; }}",
    'cycles': f"QSlider::groove:horizontal {{ height:8px; border-radius:4px; background: "
              f"qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {GREEN}, stop:0.32 {GREEN}, stop:0.62 {AMBER}, stop:1 {RED}); }} "
              f"QSlider::handle:horizontal {{ background:{GREEN}; border:2px solid {BG}; width:16px; height:16px; margin:-5px 0; border-radius:8px; }}",
}

CSV_HEADER_FIELDS = [
    'timestamp', 'pack_voltage_V', 'current_A', 'soc_pct', 'residual_capacity_Ah',
    'max_cell_mV', 'min_cell_mV', 'cell_delta_mV', 'max_temp_C', 'min_temp_C',
    'charge_mos', 'discharge_mos'
]


# ----------------------------------------------------------------- widgets
class Gauge(QWidget):
    def __init__(self, title, unit, vmin, vmax, color, parent=None):
        super().__init__(parent)
        self.title, self.unit = title, unit
        self.vmin, self.vmax = vmin, vmax
        self.color = QColor(color)
        self.value = vmin
        self.setMinimumSize(150, 150)

    def set_value(self, v):
        self.value = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(side / 200.0, side / 200.0)

        p.setPen(QPen(QColor(BORDER), 14, Qt.SolidLine, Qt.RoundCap))
        rect = QRectF(-80, -80, 160, 160)
        p.drawArc(rect, -225 * 16, -270 * 16)

        frac = 0.0
        if self.vmax > self.vmin:
            frac = max(0.0, min(1.0, (self.value - self.vmin) / (self.vmax - self.vmin)))
        p.setPen(QPen(self.color, 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, -225 * 16, int(-270 * frac * 16))

        p.setPen(QColor(TEXT))
        f = QFont('Consolas', 22); f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(-80, -14, 160, 36), Qt.AlignCenter, f"{self.value:.1f}")

        p.setPen(QColor(TEXT_MUTE))
        p.setFont(QFont('Arial', 9))
        p.drawText(QRectF(-80, -98, 160, 20), Qt.AlignCenter, self.title.upper())
        p.drawText(QRectF(-80, 22, 160, 20), Qt.AlignCenter, self.unit)


class CellArrayWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cells = []
        self.setMinimumHeight(150)

    def set_cells(self, cells):
        self.cells = cells or []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self.cells) if self.cells else 13
        gap = 6
        bar_w = max(2.0, (w - gap * (n + 1)) / n)
        vmin, vmax = 3.0, 4.2
        mean = sum(self.cells) / len(self.cells) if self.cells else 3.7

        for i in range(n):
            v = self.cells[i] if i < len(self.cells) else mean
            frac = max(0.04, min(1.0, (v - vmin) / (vmax - vmin)))
            bar_h = frac * (h - 26)
            x = gap + i * (bar_w + gap)
            y = h - 22 - bar_h
            dev = abs(v - mean)
            if v < 3.05 or v > 4.22:
                color = QColor(RED)
            elif dev > 0.05:
                color = QColor(VIOLET)
            else:
                color = QColor(TEAL_BRIGHT)
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)
            p.setPen(QColor(TEXT_MUTE))
            p.setFont(QFont('Arial', 7))
            p.drawText(QRectF(x, h - 18, bar_w, 16), Qt.AlignCenter, str(i + 1))


class Readout(QFrame):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{CARD}; border:1px solid {BORDER}; border-radius:8px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)
        cap = QLabel(label.upper()); cap.setObjectName('lblCaption')
        self.val = QLabel('—'); self.val.setObjectName('lblValue')
        lay.addWidget(cap)
        lay.addWidget(self.val)

    def set_value(self, text, color=None):
        self.val.setText(text)
        self.val.setStyleSheet(f"color:{color};" if color else f"color:{TEXT};")


# ----------------------------------------------------------------- serial: real BMS protocol
class SerialReader(QObject):
    """Auto-polls the BMS with the standard command set (0x90-0x98) and
    decodes replies using bms_protocol — the same framing already proven
    against real hardware in the Sara Controls data logger."""
    state_updated = Signal(object)     # emits a bp.BMSState snapshot
    raw_bytes = Signal(str)
    error = Signal(str)
    stopped = Signal()

    def __init__(self, port, baud):
        super().__init__()
        self.port, self.baud = port, baud
        self._running = False
        self.auto_poll = True

    def start(self):
        self._running = True
        try:
            ser = serial.Serial(self.port, self.baud, timeout=0.05)
        except Exception as e:
            self.error.emit(str(e))
            self.stopped.emit()
            return

        rx_buf = bytearray()
        cmd_idx = 0
        last_poll = 0.0
        state = bp.BMSState()

        while self._running:
            now = time.time()
            if self.auto_poll and (now - last_poll) > 0.4:
                cmd = bp.CMDS[cmd_idx % len(bp.CMDS)]
                cmd_idx += 1
                try:
                    ser.write(bp.build_request(cmd))
                except Exception as e:
                    self.error.emit(f'write error: {e}')
                last_poll = now

            try:
                data = ser.read(256)
            except Exception as e:
                self.error.emit(f'read error: {e}')
                break

            if data:
                self.raw_bytes.emit(' '.join(f'{b:02x}' for b in data))
                rx_buf.extend(data)
                frames, rx_buf = bp.drain_frames(rx_buf)
                for frame in frames:
                    bp.handle_frame(state, frame)
                    self.state_updated.emit(state)

        try:
            ser.close()
        except Exception:
            pass
        self.stopped.emit()

    def stop(self):
        self._running = False


# ----------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Sara Controls & Automation — Li-Ion Battery Digital Twin')
        self.resize(1680, 1140)

        logo_path = os.path.join(ASSETS_DIR, 'sara_logo.png')
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.real = None
        self.sim = None
        self.serial_thread = None
        self.serial_worker = None
        self.recording = False
        self.recorded_rows = []
        self.live_state = bp.BMSState()

        self._build_ui()

    # ---------------------------------------------------------- UI building
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(330)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_inner = QWidget()
        left_layout = QVBoxLayout(left_inner)
        left_layout.setSpacing(12)
        left_layout.addWidget(self._build_load_group())
        left_layout.addWidget(self._build_params_group())
        left_layout.addWidget(self._build_scenario_group())
        left_layout.addWidget(self._build_fault_group())
        left_layout.addWidget(self._build_serial_group())
        run_btn = QPushButton('▸  Run digital twin')
        run_btn.setObjectName('btnRun')
        run_btn.clicked.connect(self.run_simulation)
        left_layout.addWidget(run_btn)
        left_layout.addStretch(1)
        left_scroll.setWidget(left_inner)
        body.addWidget(left_scroll)
        self._enable_touch_scroll(left_scroll)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_inner = QWidget()
        right = QVBoxLayout(right_inner)
        right.setSpacing(12)
        right.addWidget(self._build_live_readouts())
        right.addWidget(self._build_gauges_and_cells())
        right.addWidget(self._build_charts())
        right.addWidget(self._build_verdict_group())
        right_scroll.setWidget(right_inner)
        body.addWidget(right_scroll, 1)

        self.setStyleSheet(APP_QSS + SCROLLBAR_QSS)

    def _enable_touch_scroll(self, scroll_area):
        """Lets a click-and-drag (or a finger, on a touchscreen) scroll the
        panel directly, instead of requiring precise scrollbar grabbing."""
        from PySide6.QtWidgets import QScroller
        QScroller.grabGesture(scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
        scroll_area.verticalScrollBar().setSingleStep(24)

    def _build_header(self):
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {PANEL}, stop:1 {CARD2}); "
            f"border-radius:16px; border:1px solid {BORDER}; }}"
        )
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 12, 16, 12)

        logo_path = os.path.join(ASSETS_DIR, 'sara_logo.png')
        logo_holder = QFrame()
        logo_holder.setFixedSize(46, 46)
        logo_holder.setStyleSheet("background:white; border-radius:12px;")
        logo_lay = QVBoxLayout(logo_holder)
        logo_lay.setContentsMargins(6, 6, 6, 6)
        logo_lbl = QLabel()
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            logo_lbl.setPixmap(pix.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lay.addWidget(logo_lbl)
        lay.addWidget(logo_holder)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel('SARA CONTROLS <span style="color:%s;">&amp;</span> AUTOMATION' % TEAL_BRIGHT)
        title.setStyleSheet(f"color:{TEXT}; font-size:16px; font-weight:800; letter-spacing:1.5px;")
        sub = QLabel('LI-ION BATTERY DIGITAL TWIN — CELL & PACK LEVEL SIMULATION')
        sub.setStyleSheet(f"color:{TEXT_MUTE}; font-size:10.5px; font-family:Consolas; letter-spacing:1px;")
        text_col.addWidget(title)
        text_col.addWidget(sub)
        lay.addLayout(text_col)
        lay.addStretch(1)

        self.led_log = QLabel('●  LOG')
        self.led_sim = QLabel('●  TWIN')
        self.led_fault = QLabel('●  FAULT')
        self.led_live = QLabel('●  LIVE')
        for led in (self.led_live, self.led_log, self.led_sim, self.led_fault):
            led.setStyleSheet(f"color:{TEXT_MUTE}; font-family:Consolas; font-size:10.5px; "
                               f"background:{CARD}; padding:5px 12px; border-radius:10px; border:1px solid {BORDER};")
            lay.addWidget(led)
        return header

    def _set_led(self, led, color):
        led.setStyleSheet(f"color:{color}; font-family:Consolas; font-size:10.5px; "
                           f"background:{CARD}; padding:5px 12px; border-radius:10px; border:1px solid {BORDER};")

    def _build_load_group(self):
        g = QGroupBox('01 — Load Log')
        g.setObjectName('grpLoad')
        lay = QVBoxLayout(g)
        btn_upload = QPushButton('Upload CSV log'); btn_upload.setObjectName('btnPrimary')
        btn_upload.clicked.connect(self.upload_csv)
        btn_sample = QPushButton('Use sample log instead')
        btn_sample.clicked.connect(self.use_sample_log)
        self.lbl_status = QLabel('No log loaded yet.')
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"color:{TEXT_MUTE}; font-size:10.5px;")
        self.lbl_detected = QLabel('')
        self.lbl_detected.setWordWrap(True)
        self.lbl_detected.setStyleSheet(f"color:{TEXT_MUTE}; font-family:Consolas; font-size:9.5px;")
        lay.addWidget(btn_upload)
        lay.addWidget(btn_sample)
        lay.addWidget(self.lbl_status)
        lay.addWidget(self.lbl_detected)
        return g

    def _build_params_group(self):
        g = QGroupBox('02 — Pack Parameters')
        g.setObjectName('grpParams')
        form = QFormLayout(g)
        self.sp_ah = QDoubleSpinBox(); self.sp_ah.setRange(1, 200); self.sp_ah.setValue(10); self.sp_ah.setSuffix(' Ah')
        self.sp_cells = QSpinBox(); self.sp_cells.setRange(4, 32); self.sp_cells.setValue(13)
        self.sp_cells.valueChanged.connect(self._refresh_weak_cell_options)
        self.sp_rint = QDoubleSpinBox(); self.sp_rint.setRange(5, 200); self.sp_rint.setValue(35); self.sp_rint.setSuffix(' mΩ')
        self.sp_interval = QDoubleSpinBox(); self.sp_interval.setRange(1, 60); self.sp_interval.setValue(1); self.sp_interval.setSuffix(' min')
        form.addRow('Nominal capacity', self.sp_ah)
        form.addRow('Series cell count', self.sp_cells)
        form.addRow('Internal resistance', self.sp_rint)
        form.addRow('Sample interval', self.sp_interval)
        return g

    def _slider_row(self, layout, key, label_text, vmin, vmax, default, step=1, gradient_key=None):
        row_label = QHBoxLayout()
        cap = QLabel(label_text)
        val_lbl = QLabel(''); val_lbl.setStyleSheet("font-family:Consolas; font-weight:700;")
        row_label.addWidget(cap); row_label.addStretch(1); row_label.addWidget(val_lbl)
        layout.addLayout(row_label)

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(int(vmin / step)); slider.setMaximum(int(vmax / step)); slider.setValue(int(default / step))
        if gradient_key:
            slider.setStyleSheet(SLIDER_GRADIENTS[gradient_key])
        layout.addWidget(slider)

        zone_lbl = QLabel(''); zone_lbl.setAlignment(Qt.AlignRight)
        zone_lbl.setStyleSheet(f"color:{TEXT_MUTE}; font-size:9.5px; font-weight:600;")
        layout.addWidget(zone_lbl)

        setattr(self, f'sl_{key}', slider)
        setattr(self, f'lbl_{key}_val', val_lbl)
        setattr(self, f'lbl_{key}_zone', zone_lbl)
        return slider, val_lbl, zone_lbl

    def _build_scenario_group(self):
        g = QGroupBox('03 — Twin Scenario')
        g.setObjectName('grpScenario')
        lay = QVBoxLayout(g)

        self._slider_row(lay, 'amb', 'Ambient temperature', -10, 45, 25, step=1, gradient_key='ambTemp')
        self.sl_amb.valueChanged.connect(self._update_amb_zone); self._update_amb_zone()

        lay.addWidget(QLabel('Charge / discharge pattern'))
        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems(['Constant discharge', 'Constant charge (CC)', 'Fast charge (high C)', 'Drive-cycle pulses'])
        lay.addWidget(self.cmb_pattern)

        self._slider_row(lay, 'crate', 'C-rate', 0.1, 2.0, 0.5, step=0.1, gradient_key='crate')
        self.sl_crate.valueChanged.connect(self._update_crate_zone); self._update_crate_zone()

        self._slider_row(lay, 'dur', 'Duration (min)', 5, 180, 60, step=1)
        self._slider_row(lay, 'cycles', 'Virtual aging (cycles)', 0, 1000, 0, step=10, gradient_key='cycles')
        self.sl_cycles.valueChanged.connect(self._update_cycles_zone); self._update_cycles_zone()

        self.chk_balance = QCheckBox('Active cell balancing enabled')
        self.chk_balance.setChecked(True)
        lay.addWidget(self.chk_balance)
        return g

    def _update_amb_zone(self):
        v = self.sl_amb.value()
        self.lbl_amb_val.setText(f'{v}°C')
        if v < 0 or v > 40:
            txt, color = (('COLD — REDUCED PERFORMANCE', RED) if v < 0 else ('HOT — THERMAL RISK', RED))
        elif v < 10 or v > 35:
            txt, color = (('COOL — DERATE CHARGING', AMBER) if v < 10 else ('WARM — MONITOR TEMP', AMBER))
        else:
            txt, color = ('SAFE OPERATING RANGE', GREEN)
        self.lbl_amb_zone.setText(txt)
        self.lbl_amb_zone.setStyleSheet(f"color:{color}; font-size:9.5px; font-weight:700;")
        self.lbl_amb_val.setStyleSheet(f"font-family:Consolas; font-weight:700; color:{color};")

    def _update_crate_zone(self):
        v = self.sl_crate.value() / 10.0
        self.lbl_crate_val.setText(f'{v:.1f}C')
        if v > 1.5: txt, color = 'HIGH C-RATE — STRESSES CELLS', RED
        elif v > 1.0: txt, color = 'ELEVATED — WATCH TEMP RISE', AMBER
        else: txt, color = 'LOW STRESS', GREEN
        self.lbl_crate_zone.setText(txt)
        self.lbl_crate_zone.setStyleSheet(f"color:{color}; font-size:9.5px; font-weight:700;")
        self.lbl_crate_val.setStyleSheet(f"font-family:Consolas; font-weight:700; color:{color};")

    def _update_cycles_zone(self):
        v = self.sl_cycles.value()
        self.lbl_cycles_val.setText(str(v))
        if v > 700: txt, color = 'HEAVILY AGED — LIKELY SoH LOSS', RED
        elif v > 300: txt, color = 'MODERATE WEAR', AMBER
        else: txt, color = 'LOW WEAR', GREEN
        self.lbl_cycles_zone.setText(txt)
        self.lbl_cycles_zone.setStyleSheet(f"color:{color}; font-size:9.5px; font-weight:700;")
        self.lbl_cycles_val.setStyleSheet(f"font-family:Consolas; font-weight:700; color:{color};")

    def _build_fault_group(self):
        g = QGroupBox('04 — Fault Injection')
        g.setObjectName('grpFault')
        lay = QVBoxLayout(g)
        row = QHBoxLayout()
        self.chk_weak = QCheckBox('Weak cell')
        self.cmb_weak_idx = QComboBox()
        row.addWidget(self.chk_weak); row.addStretch(1); row.addWidget(self.cmb_weak_idx)
        lay.addLayout(row)
        self._refresh_weak_cell_options()
        self.chk_sensor = QCheckBox('Thermistor dropout')
        self.chk_spike = QCheckBox('Over-current spike')
        lay.addWidget(self.chk_sensor); lay.addWidget(self.chk_spike)
        return g

    def _refresh_weak_cell_options(self):
        self.cmb_weak_idx.clear()
        for i in range(1, self.sp_cells.value() + 1):
            self.cmb_weak_idx.addItem(f'#{i}')

    def _build_serial_group(self):
        g = QGroupBox('05 — Live BMS Connection')
        g.setObjectName('grpSerial')
        lay = QVBoxLayout(g)

        row = QHBoxLayout()
        self.cmb_port = QComboBox()
        btn_refresh = QPushButton('⟳'); btn_refresh.setFixedWidth(34)
        btn_refresh.clicked.connect(self.refresh_ports)
        row.addWidget(self.cmb_port, 1); row.addWidget(btn_refresh)
        lay.addLayout(row)

        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems(['9600', '19200', '115200'])
        lay.addWidget(self.cmb_baud)

        self.btn_connect = QPushButton('Connect & Auto-poll'); self.btn_connect.setObjectName('btnPrimary')
        self.btn_connect.clicked.connect(self.toggle_serial)
        lay.addWidget(self.btn_connect)

        self.btn_record = QPushButton('● Start recording session')
        self.btn_record.clicked.connect(self.toggle_recording)
        self.btn_record.setEnabled(False)
        lay.addWidget(self.btn_record)

        self.btn_use_recording = QPushButton('Use recorded session as log')
        self.btn_use_recording.clicked.connect(self.use_recorded_session)
        self.btn_use_recording.setEnabled(False)
        lay.addWidget(self.btn_use_recording)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFixedHeight(80)
        lay.addWidget(self.console)

        note = QLabel('Uses the standard lithium BMS UART frame (0xA5 start, cmd 0x90–0x98, '
                       'checksum = sum-of-bytes & 0xFF) — same protocol proven in the Sara Controls '
                       'data logger. Read-only: never sends MOS on/off or config writes.')
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_MUTE}; font-size:9.5px;")
        lay.addWidget(note)

        if not SERIAL_AVAILABLE:
            warn = QLabel('pyserial not installed — live connection disabled. pip install pyserial')
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{RED}; font-size:10px;")
            lay.addWidget(warn)
            self.cmb_port.setEnabled(False)
            self.btn_connect.setEnabled(False)
        else:
            self.refresh_ports()
        return g

    def _build_live_readouts(self):
        g = QGroupBox('Live BMS Telemetry')
        g.setObjectName('grpLive')
        lay = QVBoxLayout(g)

        grid = QGridLayout()
        self.live_volt = Readout('Pack Voltage')
        self.live_current = Readout('Current')
        self.live_soc = Readout('SOC')
        self.live_cap = Readout('Residual Cap')
        self.live_cellmm = Readout('Max / Min Cell')
        self.live_tempmm = Readout('Max / Min Temp')
        self.live_mos = Readout('MOS State')
        self.live_cycles = Readout('Cycles')
        for i, w in enumerate([self.live_volt, self.live_current, self.live_soc, self.live_cap,
                                self.live_cellmm, self.live_tempmm, self.live_mos, self.live_cycles]):
            grid.addWidget(w, i // 4, i % 4)
        lay.addLayout(grid)

        self.live_fault_label = QLabel('No active faults reported')
        self.live_fault_label.setStyleSheet(f"color:{GREEN}; font-size:11px; padding-top:4px;")
        self.live_fault_label.setWordWrap(True)
        lay.addWidget(self.live_fault_label)
        return g

    def _build_gauges_and_cells(self):
        wrap = QFrame()
        wrap.setStyleSheet(f"QFrame{{background:{PANEL}; border:1px solid {BORDER}; border-radius:14px; border-top:3px solid {VIOLET};}}")
        lay = QVBoxLayout(wrap)

        top = QHBoxLayout()
        self.gauge_soc = Gauge('SoC', '%', 0, 100, GREEN)
        self.gauge_temp = Gauge('Pack Temp', '°C', -10, 80, AMBER)
        top.addWidget(self.gauge_soc)
        top.addWidget(self.gauge_temp)

        readouts = QGridLayout()
        self.ro_source = Readout('Source')
        self.ro_packv = Readout('Pack Voltage')
        self.ro_imbalance = Readout('Cell Imbalance')
        self.ro_current = Readout('Current')
        readouts.addWidget(self.ro_source, 0, 0)
        readouts.addWidget(self.ro_packv, 0, 1)
        readouts.addWidget(self.ro_imbalance, 1, 0)
        readouts.addWidget(self.ro_current, 1, 1)
        top.addLayout(readouts, 1)
        lay.addLayout(top)

        self.cell_array = CellArrayWidget()
        lay.addWidget(self.cell_array)

        scrub_row = QHBoxLayout()
        self.sl_scrub = QSlider(Qt.Horizontal)
        self.sl_scrub.setMinimum(0); self.sl_scrub.setMaximum(0)
        self.sl_scrub.valueChanged.connect(self.update_scrub_display)
        self.lbl_scrub_time = QLabel('t = —')
        self.lbl_scrub_time.setStyleSheet("font-family:Consolas; font-weight:700;")
        scrub_row.addWidget(QLabel('Scrub:'))
        scrub_row.addWidget(self.sl_scrub, 1)
        scrub_row.addWidget(self.lbl_scrub_time)
        lay.addLayout(scrub_row)
        return wrap

    def _build_charts(self):
        wrap = QFrame()
        wrap.setMinimumHeight(680)
        grid = QGridLayout(wrap)
        grid.setSpacing(12)
        pg.setConfigOption('background', PANEL)
        pg.setConfigOption('foreground', TEXT_MUTE)

        def make_plot(title, y_label, y_unit, x_label='Time', x_unit='min'):
            container = QFrame()
            container.setStyleSheet(f"QFrame{{background:{PANEL}; border:1px solid {BORDER}; border-radius:10px;}}")
            lay = QVBoxLayout(container)
            lay.setContentsMargins(10, 8, 10, 8)

            header = QHBoxLayout()
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color:{TEXT_MUTE}; font-size:11.5px; font-weight:700; letter-spacing:.5px; border:none;")
            header.addWidget(lbl)
            header.addStretch(1)
            hint = QLabel('scroll = zoom · drag = pan · right-drag = box zoom')
            hint.setStyleSheet(f"color:{TEXT_MUTE}; font-size:9px; border:none;")
            header.addWidget(hint)
            btn_reset = QPushButton('⤢ Reset view')
            btn_reset.setFixedWidth(100)
            header.addWidget(btn_reset)
            lay.addLayout(header)

            pw = pg.PlotWidget()
            pw.showGrid(x=True, y=True, alpha=0.15)
            pw.setBackground(PANEL)
            pw.setLabel('left', y_label, units=y_unit)
            pw.setLabel('bottom', x_label, units=x_unit)
            pw.setMinimumHeight(280)
            pw.getPlotItem().getAxis('left').setStyle(tickFont=QFont('Consolas', 9))
            pw.getPlotItem().getAxis('bottom').setStyle(tickFont=QFont('Consolas', 9))
            btn_reset.clicked.connect(lambda: pw.getPlotItem().autoRange())
            lay.addWidget(pw)
            return container, pw

        soc_box, self.plot_soc = make_plot('STATE OF CHARGE', 'SoC', '%')
        volt_box, self.plot_volt = make_plot('PACK VOLTAGE', 'Voltage', 'V')
        temp_box, self.plot_temp = make_plot('PACK TEMPERATURE — TWIN VS SENSOR', 'Temp', '°C')
        spread_box, self.plot_spread = make_plot('CELL VOLTAGE SPREAD', 'Voltage', 'V')

        grid.addWidget(soc_box, 0, 0)
        grid.addWidget(volt_box, 0, 1)
        grid.addWidget(temp_box, 1, 0)
        grid.addWidget(spread_box, 1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return wrap

    def _build_verdict_group(self):
        g = QGroupBox('Usability Verdict')
        g.setObjectName('grpVerdict')
        self.verdict_group = g
        lay = QVBoxLayout(g)
        self.lbl_badge = QLabel('Run a scenario to generate a usability assessment.')
        self.lbl_badge.setStyleSheet(f"color:{TEXT_MUTE}; font-size:11.5px;")
        lay.addWidget(self.lbl_badge)

        metrics = QGridLayout()
        self.ro_soh = Readout('Estimated SoH')
        self.ro_cap = Readout('Effective capacity')
        self.ro_peaktemp = Readout('Peak pack temp')
        self.ro_maximbalance = Readout('Max cell imbalance')
        metrics.addWidget(self.ro_soh, 0, 0)
        metrics.addWidget(self.ro_cap, 0, 1)
        metrics.addWidget(self.ro_peaktemp, 0, 2)
        metrics.addWidget(self.ro_maximbalance, 0, 3)
        lay.addLayout(metrics)

        self.fault_list = QListWidget()
        self.fault_list.setFixedHeight(90)
        lay.addWidget(self.fault_list)
        return g

    # ---------------------------------------------------------- CSV loading
    def upload_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open BMS CSV log', '', 'CSV files (*.csv)')
        if not path:
            return
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        self._load_csv_text(text, path.split('/')[-1])

    def use_sample_log(self):
        text = te.generate_sample_csv(cell_count=self.sp_cells.value(), nominal_ah=self.sp_ah.value())
        self._load_csv_text(text, 'sample_log.csv (synthetic)')

    def _load_csv_text(self, text, label):
        try:
            real, cols = te.parse_csv_text(
                text, nominal_ah=self.sp_ah.value(), cell_count=self.sp_cells.value(),
                sample_interval_min=self.sp_interval.value()
            )
        except Exception as e:
            self.lbl_status.setText(f'Could not parse this file: {e}')
            return
        self.real = real
        self.lbl_status.setText(f'Loaded "{label}" — {len(real.time)} samples, {real.time[-1]:.0f} min span.')
        self._set_led(self.led_log, GREEN)
        self.lbl_detected.setText(
            f"time:{cols['time'] or 'assumed'}  packV:{cols['pack_v'] or 'sum of cells'}  "
            f"current:{cols['current'] or '—'}  SOC:{cols['soc'] or 'estimated'}  "
            f"temps:{','.join(cols['temps']) or '—'}  cells:{len(cols['cells'])} found"
        )
        self._render_preview()

    def _render_preview(self):
        if not self.real:
            return
        self._plot_combined(real_len=len(self.real.time),
                             time=self.real.time, soc=self.real.soc, pack_v=self.real.pack_v,
                             temp_twin=self.real.temp, temp_sensor=self.real.temp,
                             cell_v=self.real.cell_v)
        self._setup_scrubber(len(self.real.time) - 1)

    # ---------------------------------------------------------- simulation
    def run_simulation(self):
        pattern_map = {0: 'discharge', 1: 'charge', 2: 'fastcharge', 3: 'pulse'}
        params = te.SimParams(
            nominal_ah=self.sp_ah.value(),
            cell_count=self.sp_cells.value(),
            r_int_ohm=self.sp_rint.value() / 1000.0,
            ambient_c=self.sl_amb.value(),
            pattern=pattern_map[self.cmb_pattern.currentIndex()],
            c_rate=self.sl_crate.value() / 10.0,
            duration_min=self.sl_dur.value(),
            cycles=self.sl_cycles.value(),
            balancing_on=self.chk_balance.isChecked(),
            fault_weak_cell=self.chk_weak.isChecked(),
            weak_cell_idx=self.cmb_weak_idx.currentIndex() if self.cmb_weak_idx.count() else 0,
            fault_sensor=self.chk_sensor.isChecked(),
            fault_spike=self.chk_spike.isChecked(),
        )
        self.sim = te.run_simulation(params, self.real)
        self._set_led(self.led_sim, GREEN)
        if any(f['alert'] for f in self.sim.fault_log):
            self._set_led(self.led_fault, RED)

        real_len = len(self.real.time) if self.real else 0
        time = (self.real.time if self.real else []) + self.sim.time
        soc = (self.real.soc if self.real else []) + self.sim.soc
        pack_v = (self.real.pack_v if self.real else []) + self.sim.pack_v
        temp_twin = (self.real.temp if self.real else []) + self.sim.temp
        temp_sensor = (self.real.temp if self.real else []) + self.sim.temp_sensor
        cell_v = (self.real.cell_v if self.real else []) + self.sim.cell_v

        self._plot_combined(real_len, time, soc, pack_v, temp_twin, temp_sensor, cell_v)
        self._setup_scrubber(len(time) - 1)
        self._render_verdict()

    def _plot_combined(self, real_len, time, soc, pack_v, temp_twin, temp_sensor, cell_v):
        self._combined = dict(real_len=real_len, time=time, soc=soc, pack_v=pack_v,
                               temp_twin=temp_twin, temp_sensor=temp_sensor, cell_v=cell_v)
        t_real, t_twin = time[:real_len], time[max(real_len - 1, 0):]

        for plot in (self.plot_soc, self.plot_volt, self.plot_temp, self.plot_spread):
            plot.clear()

        def draw(plot, arr):
            a_real, a_twin = arr[:real_len], arr[max(real_len - 1, 0):]
            if a_real:
                plot.plot(t_real, a_real, pen=pg.mkPen(TEAL_BRIGHT, width=2), name='logged')
            if a_twin:
                plot.plot(t_twin, a_twin, pen=pg.mkPen(VIOLET, width=2), name='twin')

        draw(self.plot_soc, soc)
        draw(self.plot_volt, pack_v)
        self.plot_temp.plot(time, temp_twin, pen=pg.mkPen(VIOLET, width=2), name='twin(true)')
        self.plot_temp.plot(time, temp_sensor, pen=pg.mkPen(RED, width=2, style=Qt.DashLine), name='sensor')

        max_c = [max(c) if c else None for c in cell_v]
        avg_c = [(sum(c) / len(c)) if c else None for c in cell_v]
        min_c = [min(c) if c else None for c in cell_v]
        if all(v is not None for v in max_c):
            self.plot_spread.plot(time, max_c, pen=pg.mkPen(TEAL_BRIGHT, width=2), name='max')
            self.plot_spread.plot(time, avg_c, pen=pg.mkPen(TEXT_MUTE, width=1.5), name='avg')
            self.plot_spread.plot(time, min_c, pen=pg.mkPen(VIOLET, width=2), name='min')

    def _setup_scrubber(self, max_idx):
        self.sl_scrub.setMaximum(max(0, max_idx))
        self.sl_scrub.setValue(max(0, max_idx))
        self.update_scrub_display()

    def update_scrub_display(self):
        c = getattr(self, '_combined', None)
        if not c or not c['time']:
            return
        idx = min(self.sl_scrub.value(), len(c['time']) - 1)
        t = c['time'][idx]
        self.lbl_scrub_time.setText(f't = {t:.0f} min')

        cells = c['cell_v'][idx] if idx < len(c['cell_v']) else []
        self.cell_array.set_cells(cells)

        is_twin = idx >= c['real_len']
        self.ro_source.set_value('TWIN' if is_twin else 'LOGGED', VIOLET if is_twin else TEAL_BRIGHT)
        soc_v = c['soc'][idx] if idx < len(c['soc']) else None
        pv = c['pack_v'][idx] if idx < len(c['pack_v']) else None
        temp = c['temp_twin'][idx] if idx < len(c['temp_twin']) else None
        self.ro_packv.set_value(f'{pv:.2f}V' if pv is not None else '—')
        spread_mv = (max(cells) - min(cells)) * 1000 if cells else None
        self.ro_imbalance.set_value(f'{spread_mv:.0f}mV' if spread_mv is not None else '—',
                                     RED if (spread_mv and spread_mv > 80) else None)
        if soc_v is not None:
            self.gauge_soc.set_value(soc_v)
        if temp is not None:
            self.gauge_temp.set_value(temp)
        self.ro_current.set_value('—')

    def _render_verdict(self):
        v = te.usability_verdict(self.sim)
        color = {'good': GREEN, 'marginal': AMBER, 'poor': RED}[v['level']]
        self.verdict_group.setStyleSheet(f"QGroupBox#grpVerdict {{ border-top: 3px solid {color}; }}")
        self.lbl_badge.setText(v['label'])
        self.lbl_badge.setStyleSheet(f"color:{color}; font-size:14px; font-weight:800; padding:6px 0;")

        self.ro_soh.set_value(f"{v['soh']:.1f}%")
        self.ro_cap.set_value(f"{self.sim.effective_ah:.2f} Ah")
        self.ro_peaktemp.set_value(f"{v['peak_temp']:.1f}°C", RED if v['peak_temp'] > 45 else None)
        self.ro_maximbalance.set_value(f"{v['max_imbalance_mv']:.0f} mV", RED if v['max_imbalance_mv'] > 80 else None)

        self.fault_list.clear()
        if not self.sim.fault_log:
            self.fault_list.addItem('No faults logged during this scenario.')
        for f in self.sim.fault_log:
            item = QListWidgetItem(f"t={f['t']:.0f}min — {f['msg']}")
            if f['alert']:
                item.setForeground(QColor(RED))
            self.fault_list.addItem(item)

    # ---------------------------------------------------------- live serial (real protocol)
    def refresh_ports(self):
        if not SERIAL_AVAILABLE:
            return
        self.cmb_port.clear()
        ports = list(list_ports.comports())
        for p in ports:
            self.cmb_port.addItem(f'{p.device} — {p.description}', p.device)
        if not ports:
            self.cmb_port.addItem('No serial ports found', None)

    def toggle_serial(self):
        if self.serial_thread is not None:
            self._stop_serial()
            return
        port = self.cmb_port.currentData()
        if not port:
            self.console.appendPlainText('No serial port selected.')
            return
        baud = int(self.cmb_baud.currentText())
        self.serial_thread = QThread()
        self.serial_worker = SerialReader(port, baud)
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_thread.started.connect(self.serial_worker.start)
        self.serial_worker.state_updated.connect(self._on_state_updated)
        self.serial_worker.error.connect(lambda msg: self.console.appendPlainText(f'[error] {msg}'))
        self.serial_worker.stopped.connect(self._on_serial_stopped)
        self.serial_thread.start()
        self.btn_connect.setText('Disconnect')
        self.btn_record.setEnabled(True)
        self._set_led(self.led_live, GREEN)
        self.console.appendPlainText(f'Connected to {port} @ {baud} baud — auto-polling 0x90-0x98.')

    def _stop_serial(self):
        if self.serial_worker:
            self.serial_worker.stop()
        if self.serial_thread:
            self.serial_thread.quit()
            self.serial_thread.wait(1500)
        self.serial_thread = None
        self.serial_worker = None
        self.btn_connect.setText('Connect & Auto-poll')
        self.btn_record.setEnabled(False)
        self._set_led(self.led_live, TEXT_MUTE)

    def _on_serial_stopped(self):
        self.console.appendPlainText('Serial connection closed.')

    def _on_state_updated(self, state: bp.BMSState):
        self.live_state = state
        self.live_volt.set_value(f'{state.volt:.2f}V' if state.volt is not None else '—')
        self.live_current.set_value(f'{state.current:.2f}A' if state.current is not None else '—')
        self.live_soc.set_value(f'{state.soc:.1f}%' if state.soc is not None else '—')
        self.live_cap.set_value(f'{state.residual_ah:.2f}Ah' if state.residual_ah is not None else '—')
        cmm = '—'
        if state.max_cell_mv is not None and state.min_cell_mv is not None:
            cmm = f'{state.max_cell_mv/1000:.3f} / {state.min_cell_mv/1000:.3f} V'
        self.live_cellmm.set_value(cmm)
        tmm = '—'
        if state.max_temp is not None and state.min_temp is not None:
            tmm = f'{state.max_temp} / {state.min_temp} °C'
        self.live_tempmm.set_value(tmm, RED if (state.max_temp is not None and state.max_temp > 55) else None)
        mos = '—'
        if state.charge_mos is not None or state.discharge_mos is not None:
            c = 'CHG·ON' if state.charge_mos else 'CHG·OFF'
            d = 'DSG·ON' if state.discharge_mos else 'DSG·OFF'
            mos = f'{c}  {d}'
        self.live_mos.set_value(mos, RED if state.charge_mos is False else None)
        self.live_cycles.set_value(str(state.cycles) if state.cycles is not None else '—')

        live_cells = state.cell_list()
        if live_cells:
            self.cell_array.set_cells(live_cells)

        if state.faults:
            self.live_fault_label.setText('⚠ ' + ', '.join(state.faults))
            self.live_fault_label.setStyleSheet(f"color:{RED}; font-size:11px; padding-top:4px; font-weight:600;")
            self._set_led(self.led_fault, RED)
        else:
            self.live_fault_label.setText('No active faults reported')
            self.live_fault_label.setStyleSheet(f"color:{GREEN}; font-size:11px; padding-top:4px;")

        if self.recording:
            self._capture_live_row(state)

    def _capture_live_row(self, state: bp.BMSState):
        row = {
            'timestamp': datetime.now().isoformat(),
            'pack_voltage_V': state.volt, 'current_A': state.current, 'soc_pct': state.soc,
            'residual_capacity_Ah': state.residual_ah,
            'max_cell_mV': state.max_cell_mv, 'min_cell_mV': state.min_cell_mv,
            'cell_delta_mV': (state.max_cell_mv - state.min_cell_mv)
                              if (state.max_cell_mv is not None and state.min_cell_mv is not None) else None,
            'max_temp_C': state.max_temp, 'min_temp_C': state.min_temp,
            'charge_mos': None if state.charge_mos is None else int(state.charge_mos),
            'discharge_mos': None if state.discharge_mos is None else int(state.discharge_mos),
        }
        for i, mv in enumerate(state.cells):
            if mv is not None:
                row[f'cell_{i+1}_mV'] = mv
        self.recorded_rows.append(row)
        self.btn_record.setText(f'■ Stop recording ({len(self.recorded_rows)} rows)')

    def toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.recorded_rows = []
            self.btn_record.setText('■ Stop recording (0 rows)')
            self.console.appendPlainText('--- recording started ---')
        else:
            self.recording = False
            self.btn_record.setText('● Start recording session')
            self.console.appendPlainText(f'--- recording stopped: {len(self.recorded_rows)} rows captured ---')
            self.btn_use_recording.setEnabled(len(self.recorded_rows) > 0)

    def use_recorded_session(self):
        if not self.recorded_rows:
            return
        headers = list(CSV_HEADER_FIELDS)
        max_cells = max((sum(1 for k in row if k.startswith('cell_')) for row in self.recorded_rows), default=0)
        headers += [f'cell_{i+1}_mV' for i in range(max_cells)]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers, restval='')
        w.writeheader()
        w.writerows(self.recorded_rows)
        self._load_csv_text(buf.getvalue(), 'live recorded session')

    def closeEvent(self, event):
        self._stop_serial()
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
