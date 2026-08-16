# Sara Controls & Automation — Li-Ion Battery Digital Twin

A native instrument-panel desktop application (PySide6 + pyqtgraph) — branded, and wired to the
**real BMS protocol** already proven in your data-logging software: standard lithium BMS UART
framing (start `0xA5`, host `0x40`, commands `0x90`–`0x98`, checksum = sum-of-bytes & 0xFF).

## What's new in this version

- **Your branding**: logo, company name, and color system (teal/violet/amber/rose dark theme)
  pulled directly from your `li-ion-battery-data-logging-software6.html` file.
- **Real protocol, not a placeholder**: `bms_protocol.py` is a byte-exact Python port of your
  JS frame builder/parser — auto-polls 0x90–0x98, decodes pack voltage, current, SOC, per-cell
  voltages, temperatures, MOS states, cycle count, and all 48 fault-bit flags.
  This replaces the earlier version's generic "guess the CSV format" placeholder entirely.
- **Live BMS Telemetry panel**: pack voltage, current, SOC, residual capacity, max/min cell,
  max/min temp, MOS state, cycles, and an active fault strip — updating in real time as frames
  arrive, exactly like the "Real-Time Values" panel in your web tool.
- **CSV compatibility**: the twin's CSV importer now recognizes your exact export headers
  (`pack_voltage_V`, `current_A`, `soc_pct`, `cell_1_mV`, etc.) automatically. A CSV exported from
  your existing web logger loads straight into the twin with no relabeling.
- **Record → twin pipeline**: hit "Start recording session" while connected to a real pack, stop
  it, then "Use recorded session as log" — the recorded telemetry (in the same column format as
  your logger's CSV export) feeds directly into the digital twin scenario engine.

## Files

```
packtwin-python/
├── main.py                    ← the GUI (PySide6 + pyqtgraph), Sara Controls branded
├── bms_protocol.py              ← real JBD/Xiaoxiang BMS UART protocol — frame build/parse/decode
├── twin_engine.py                 ← simulation physics, CSV parsing — no GUI dependencies
├── assets/sara_logo.png            ← extracted from your HTML file
├── requirements.txt
├── sample_bms_log.csv               ← ready-to-use demo log
├── START_PACKTWIN.bat/.command        ← one-click run for your own testing
├── .github/workflows/build.yml          ← automatic Windows+Mac build pipeline
└── README.md
```

## For selling this: build a real .exe / .app (no Python visible to your client)

This is the setup for handing your client a normal-looking installer — no Python, no terminal, no
"install this first" step. It uses a free GitHub service to build the real Windows `.exe` and Mac
`.app` for you automatically, in the cloud, even though you don't own either machine yourself.

**One-time setup (about 10 minutes):**

1. Create a free account at **github.com** if you don't have one.
2. Click the **+** in the top right → **New repository**. Name it anything (e.g. `packtwin`).
   Leave it Public, don't add a README, click **Create repository**.
3. On the empty repo page, click **uploading an existing file**.
4. Drag this entire `packtwin-python` folder's contents into the browser window (all the files:
   `main.py`, `twin_engine.py`, `requirements.txt`, the `.github` folder, etc.) and click
   **Commit changes**. No command line needed — this is a plain drag-and-drop upload.
5. Click the **Actions** tab near the top of the repo page.
6. You'll see "Build PACKTWIN installers" — click it, then click **Run workflow** → **Run workflow**.
7. Wait about 5–8 minutes (it's building on a real Windows machine and a real Mac at the same time,
   in the cloud). Refresh the page — when the two jobs show green checkmarks, it's done.
8. Click into the finished run. Near the bottom, under **Artifacts**, you'll see
   **PACKTWIN-Windows** and **PACKTWIN-Mac** — click each to download.

That's it — `PACKTWIN-Windows.zip` contains a plain `PACKTWIN.exe` your Windows clients can
double-click, no install of anything else needed. `PACKTWIN-Mac.zip` contains `PACKTWIN.app` for
Mac clients (same deal — right-click → Open the first time, since it isn't Apple-notarized).

**Every time you change the app later:** repeat steps 3–8 (upload the changed files, run the
workflow again) to get a fresh installer. It's the same 5 minutes each time, no new setup.

### Optional next step: a proper installer wizard

Right now clients get a single `.exe` — professional enough for most training-kit use. If you
later want a "Setup.exe" style install wizard with your logo, Start Menu shortcut, and an
uninstaller, that's [Inno Setup](https://jrsoftware.org/isinfo.php) (free, Windows-only tool) —
happy to build that script too when you're ready for it.

## Easiest way to run it yourself while developing (no command line needed)

1. Install Python once: go to **python.org/downloads**, download the installer, run it.
   - **Windows**: on the first screen, tick **"Add python.exe to PATH"** before clicking Install.
   - **Mac**: just run the installer normally.
2. Double-click the right file for your computer:
   - **Windows** → `START_PACKTWIN.bat`
   - **Mac** → `START_PACKTWIN.command`
     (Mac may show a security warning the first time — right-click the file → **Open** → **Open**,
     since it isn't from a registered Apple developer.)

That script installs everything the app needs and launches it, automatically, every time. Nothing
else to type. (This is for *your own* testing while building the app — your clients should get the
`.exe`/`.app` from the Actions build above instead, so they never see Python at all.)

## Manual way (if you're comfortable with a terminal)

You need Python 3.9+ on your machine. Then, in this folder:

```
pip install -r requirements.txt
python main.py
```

- **01 — Load Log**: upload your BMS CSV, or click "Use sample log instead" to try it immediately
  with the included `sample_bms_log.csv`.
- **02 — Pack Parameters**: capacity, cell count, internal resistance.
- **03 — Twin Scenario**: ambient temp / C-rate / duration / virtual aging sliders — same
  green→yellow→red danger-zone coloring as the browser version.
- **04 — Fault Injection**: weak cell, thermistor dropout, over-current spike.
- **05 — Live Serial**: pick your BMS's COM/tty port and baud rate, hit Connect. Incoming lines
  show in the console. Hit "Start recording session" to buffer a live session, "Stop recording",
  then "Use recorded session as log" to feed it straight into the twin — same workflow as
  uploading a CSV, just captured live.
- **▸ Run digital twin**: runs the scenario instantly (it's just a fast loop — no waiting, same
  as the browser version).

The gauges, cell-array bars, and 4 strip charts update as you drag the **scrub** slider under the
cell array, walking through logged time and twin-projected time.

## About the live serial format

Your smart BMS's actual line format is unknown to this app. Right now it assumes each incoming
line is a comma-separated row matching this header:

```
Timestamp,PackVoltage,Current,Temp1,Temp2,SOC,Cell1,Cell2,...,Cell13
```

That's set near the top of `MainWindow.__init__` in `main.py` as `self.recorded_header`. If your
BMS sends a different column order or a different set of fields, edit that one line to match —
everything downstream (column detection, parsing) is the same flexible auto-detect logic used for
CSV uploads, so it doesn't need to match exactly, just be comma-separated with recognizable
headers (containing "volt", "current"/"amp", "temp", "soc", "cell1" etc.).

## 3. If you *do* have access to a Windows PC and a Mac yourself

You can skip GitHub Actions entirely and just run PyInstaller locally on each machine:

```
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name PACKTWIN --add-data "sample_bms_log.csv:." main.py
```

(On Windows, use a semicolon instead of a colon: `"sample_bms_log.csv;."`)
PyInstaller doesn't reliably cross-build, so this only works run separately on each OS — which is
exactly the problem the GitHub Actions setup above solves if you don't have both machines.

## Files

```
packtwin-python/
├── main.py                    ← the GUI (PySide6 + pyqtgraph)
├── twin_engine.py               ← simulation physics, CSV parsing — no GUI dependencies, testable alone
├── requirements.txt
├── sample_bms_log.csv            ← ready-to-use demo log
├── START_PACKTWIN.bat/.command     ← one-click run for your own testing
├── .github/workflows/build.yml      ← automatic Windows+Mac build pipeline (see above)
└── README.md
```
