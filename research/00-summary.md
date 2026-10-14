# Snapmaker U1 — Second Row of Toolheads: Research Summary

Date: 2026-10-14. Sources: the reference repos in the README, shallow-cloned into `refs/` (gitignored). Detailed reports:

| # | Report | Scope |
|---|--------|-------|
| 01 | [01-hardware.md](01-hardware.md) | Mechanics, docks, electronics, filament path |
| 02 | [02-klipper-firmware.md](02-klipper-firmware.md) | Klipper fork, toolchange logic, hardcoded "4" table |
| 03 | [03-host-software-ui.md](03-host-software-ui.md) | Moonraker, Fluidd, touchscreen, Snapmaker apps |
| 04 | [04-slicer-profiles.md](04-slicer-profiles.md) | OrcaSlicer fork, U1 machine profiles |
| 05 | [05-extended-firmware.md](05-extended-firmware.md) | Community firmware, build/flash/recovery path |
| 06 | [06-wiki-and-stacked-docks.md](06-wiki-and-stacked-docks.md) | Official wiki check (corrections) and the stacked dock row / lift concept |

> Update 2026-10-15: the official wiki has now been read (text dumps in [wiki/](wiki/)). Corrections are in report 06; for example, the latch slide is 8.5 mm, not ~10 mm.

> Caveat: web access (Snapmaker wiki, GitHub issues/discussions) was declined during research, so findings come from source code and configs only. Physical dimensions beyond the configured travel limits, PSU rating, and community discussion are **unverified**.

## Verdict

**Software is very doable. The mechanics are the real obstacle.**

- The firmware is already mostly data-driven per tool. Tools are discovered from `[extruderN]` sections, and each has its own park/pick position, offsets and toolhead MCU.
- The slicer supports 64 tools.
- The open host software (Moonraker, Fluidd) needs only trivial changes.
- There is **no physical space for a second dock row in the current XY envelope**. The docks already sit at the back edge and span the full X travel.

## Layer-by-layer

### 1. Mechanics: the main blocker
- The 4 docks are at `Y=332.2` with X at 35 / 102.7 / 170.2 / 237.7 (`refs/u1-klipper/lava/printer.cfg:694,859,998,1136`). Y travel ends at `335` (`:149`) and X spans `0–271` (`:128`).
- The bed moves in Z, so the docks share the gantry's XY plane and can't be stacked vertically.
- Docking is pure XY motion: move in along Y, then a ~10 mm X slide to latch or release. Any reachable XY spot with ~10 mm of free X can host a dock.
- Candidate layouts:

| Option | Idea | Cost |
|---|---|---|
| **A. Front row** | Docks at the front, at Y < 0 or by giving up print depth | ~80 mm less print depth unless the frame is extended; mirrored pick/park moves in firmware |
| **B. Extended Y** | Longer Y rails/frame; second row behind or in front | Major frame/enclosure modification |
| **C. Tool carousel/shuttle** | A motorised carrier swaps a second set of heads into the existing 4 dock slots | No firmware motion changes; an extra axis plus logic; complex mechanics |

### 2. Electronics
- Each toolhead is its own Klipper MCU (likely AT32F415) on USB. MCUs are identified by **hub port**, and all 4 ports are used. Four more heads need **another USB hub**. The toolhead firmware is identical across heads, so no MCU firmware changes are needed.
- The dock-presence sensors are 4 analog pins on the main MCU (PB0, PC4, PC5, PB1). Only ~3 ADC pins look free, and it's unknown whether they reach a connector. A **small extra MCU board** (e.g. RP2040 running Klipper) is the clean option, since the sensor code also accepts digital inputs.
- The filament system is sized for exactly 4: 2 feeder modules × 2 channels, and 2 NFC readers × 2 antennas. Tools 5–8 would **lack auto-feed and RFID** unless hardware is added. Manual loading is an acceptable first step.
- Power: the firmware heats at most 2 hotends at once, and parked heads are held at half power. PSU headroom is unknown.

### 3. Firmware (Klipper fork): moderate Python and macro work
Hard limits (verified):
- `PHYSICAL_EXTRUDER_NUM = 4`, a fixed constant rather than a config value, at `refs/u1-klipper/klippy/extras/print_task_config.py:9` and `refs/u1-klipper/klippy/extras/print_stats.py:10`. This rejects any print mapped to physical tool ≥ 4.
- `max_physical_extruder_num: 4` at `refs/u1-klipper/lava/printer.cfg:115`, enforced in `toolhead.py`.
- `MAX_EXTRUDERS = 4` at `refs/u1-klipper/klippy/kinematics/extruder.py:936`. Switch-error analysis silently gives up above 4.

Other changes needed (full table of ~34 sites in report 02):
- Lost-MCU handling only knows e0–e3 (`mcu.py`, `klippy.py`, `serialhdl.py`).
- Flow calibration and XYZ-offset calibration lists are sized for 4.
- Status and error-code tables cover tools 0–3 only.
- Many T0–T3 macros live in `lava/fluidd.cfg` and `lava/xyz_offset_calibration.cfg`. The existing placeholder `T4`–`T7` macros must be removed, because they would collide with real tools.
- Option A/B layouts need a **per-tool dock-side setting** with mirrored park/pick moves. The current code assumes docks are behind the Y=250 idle line (`extruder.py:1567,1584,1662,1679`), and the homing safe-zone logic must match.

### 4. Host software and UI
- **Moonraker**: three hardcoded spots in `machine.py`: the extruder name list and two nozzle-diameter lists of length 4. Everything else is length-agnostic. 3MF files must still report model "Snapmaker U1".
- **Fluidd**: stock upstream with no Snapmaker changes. It auto-discovers 8 extruders.
- **Closed source, likely assumes 4, can't be modified**:
  - The touchscreen `/usr/bin/gui`.
  - The Snapmaker Orca device page, with its filament→tool mapping dialog.
  - Snapmaker Control.
  - `unisrv`, the cloud service.
  - The mobile app.

  The way around these is HelixScreen on the touchscreen (already supported by the Extended Firmware) plus Fluidd. The filament→tool **mapping step would have to be rebuilt** in an open UI or done with macros.

### 5. Slicer and profiles: profile-only work
- The fork supports 64 tools. The tool count comes from the length of the per-tool arrays.
- The toolchange G-code is already generic over `n`.
- Only `machine_start_gcode` lists T0–T3 explicitly. Rewrite it with `is_extruder_used[n]` guards, using the Prusa XL as a template.
- Inherit from `Snapmaker U1 (0.4 nozzle)` and **keep the model name "Snapmaker U1"**. Wipe-tower and printer-sync features check for that exact name.

### 6. Deployment path
- The Extended Firmware repackages the stock image (an `SNMK` container that is checksummed, **not signed**). It installs via the stock Local Update and keeps an A/B slot for recovery.
- The overlay mechanism can patch Klipper Python modules and configs. Extra `.cfg` files in `extended/klipper/` are loaded without a rebuild.
- A **toolhead MCU simulator** (`41-feature-toolhead-mcu-simulator`) lets e4–e7 be faked, so the 8-tool software stack can be built and tested **before any hardware exists**.

## Recommended roadmap

1. **Software proof-of-concept (no hardware)**
   - Fork the Extended Firmware and create a personal overlay.
   - Make the tool count configurable: replace the three constants with config values and generalise the e0–e3 lists.
   - Add `[extruder4-7]` and `[mcu e4-e7]` backed by the MCU simulator, and remove the placeholder T4–T7 macros.
   - Patch Moonraker `machine.py` and create an 8-tool Orca profile.
   - Test with a dry-run print that calls T0–T7 through Fluidd or HelixScreen.
2. **Mechanical study**
   - Measure the real frame: free depth behind the docks, the area in front of the bed, and cable and umbilical routing.
   - Pick layout A, B or C, then CAD the dock brackets and check the 10 mm X-latch clearance.
3. **Electrical bring-up**
   - Add a second USB hub (power budget!) and an extra MCU for the dock sensors.
   - Connect one real 5th toolhead and validate pick/park, offsets and lost-MCU handling.
4. **Scale to 8 tools**, then optionally add a third feeder module and RFID channels.
5. **Upstream-friendly cleanup**: send the "N tools from config" generalisation to the Extended Firmware project. It's useful even without a second row, e.g. for the existing T4–T31 logical-tool work.

## Top open questions
- Physical frame depth behind the docks and in front of the bed; enclosure clearance.
- PSU wattage and 24 V/5 V headroom for 4 more heads and a hub.
- USB hub chip; spare host USB ports; whether CAN is wired to a connector.
- Spare main-MCU pins on accessible connectors.
- Toolhead MCU: AT32F415 vs AT32F403A (the sources disagree).
- How the closed touchscreen `gui` and `unisrv` behave when Klipper reports 8 extruders (crash vs. ignore).
- Community activity (GitHub issues/discussions, wiki); not yet reviewed because web access was declined.
