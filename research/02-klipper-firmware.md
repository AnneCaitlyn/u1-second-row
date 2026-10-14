# 02 - Klipper firmware (Snapmaker u1-klipper) - second row of toolheads

Source analysed: `C:\Users\N\u1-second-row\refs\u1-klipper` (shallow clone, single commit "Release firmware version 1.6.0").
Machine config lives in `refs\u1-klipper\lava\` (`printer.cfg`, `fluidd.cfg`, `xyz_offset_calibration.cfg`, MCU Kconfig snapshots).
`refs\SnapmakerU1-Extended-Firmware` only adds overlay cfgs (faulty_toolhead*, faulty_toolhead*_mcu (toolhead MCU simulator), afc.cfg, filament_feeders_popstation_mini.cfg, disable-rfid-reader.cfg); it does not contain a different printer.cfg.

All paths below are relative to `refs\u1-klipper\` unless stated otherwise.

---

## Key findings

1. **Tool-change core is mostly N-generic.** Extruders are discovered with `for i in range(99)` (`klippy/kinematics/extruder.py:2200-2232`); every `[extruderN]` that has `xy_park_position` automatically gets `Tn`, `PARK_EXTRUDERN`, `PICK_EXTRUDERN`, `MOVE_TO_XY_IDLE_POSITION_EXTRUDERN` (`extruder.py:544-550`). Park detection (`klippy/extras/park_detector.py`) and activation status (`extruder.py:830-853`) iterate over `extruder_list`, not a fixed 4.
2. **But "4" is hardcoded in ~15 places** (error-decoding tables, `PHYSICAL_EXTRUDER_NUM = 4` module constant in `print_task_config.py`, MCU-loss logic in `mcu.py`/`klippy.py`/`serialhdl.py`, flow calibrator, XYZ offset calibrator, state-machine action codes, and many macros). None of them is hard to change, but **config-only is not enough**: at minimum `print_task_config.py`, `flow_calibrator.py`, `probe_inductance_coil.py`, `extruder.py` (error analysis), `mcu.py`/`klippy.py`/`serialhdl.py` and the macro files need edits. With >4 tools, `analyze_switch_extruder_error` silently returns `None` (`extruder.py:936-939`), so detailed switch-error reporting is lost unless fixed.
3. **The pick/park motion assumes all docks are at the rear (`park_y > y_idle`).** `max(park_y - insertion_buffer, y_idle)` (`extruder.py:1584`, `1679`) and `if pos[1] > y_idle_position` (`1567`, `1662`, `1852`, `2074`) encode "the dock zone is Y > y_idle". A second row anywhere other than further back needs a per-tool "approach direction / dock side" parameter and mirrored logic. Y travel is 0..335 and the current docks are already at Y=332.2, so **there is no room for a rear row without frame changes**.
4. **Toolheads are plain Klipper MCUs on USB, addressed by hub port path.** `[mcu e0..e3]` use `/dev/serial/by-path/platform-xhci-hcd.0.auto-usb-0:1.{3,4,2,1}:1.0` (`lava/printer.cfg:15-28`). Toolhead firmware is identical for all heads (AT32F415, USB-CDC, no tool ID baked in), so adding `[mcu e4..e7]` needs only more USB ports (another hub) - no firmware change. CAN is compiled in but not used.
5. **Main-board resources sized for 4:** dock "parked" sensing uses 4 main-MCU ADC pins (PB0/PC4/PC5/PB1), filament feeders are 2 modules x 2 channels (`FEED_CHANNEL_NUMS = 2`), RFID is 2 readers x 2 channels (`FM175XX_CHANNEL_NUMS = 4`, `FILAMENT_DT_CHANNEL_NUMS = 4`). These limit auto-feed/RFID to 4 tools unless more hardware is added; tools 5-8 could run without auto-feed/RFID.
6. **Logical-vs-physical extruder mapping already exists** (`max_logical_extruder_num: 32`, `max_physical_extruder_num: 4`; macros `T4..T31` call `SWITCH_OF_EXTENDED_EXTRUDER`). With 8 physical tools the `T4..T7` macros in `fluidd.cfg` would collide with the native `T4..T7` commands and must be removed/renumbered.
7. **Verdict:** 8 tools is feasible in firmware with a moderate patch set (estimated a few hundred lines Python + macro rewrites), provided the mechanics solve dock placement. The hardest firmware piece is a direction-aware pick/park + safe-zone logic for a non-rear dock row; everything else is mechanical generalisation from 4 to N.

---

## 1. Snapmaker-specific code vs upstream Klipper

### New Python modules (not in upstream), `klippy/extras/` (line counts)
| Module | Lines | Purpose |
|---|---|---|
| park_detector.py | 95 | Dock/tool presence: park pin (main MCU ADC) + active pin + grab_valid pin (toolhead MCU) -> ACTIVATE / PARKED / UNKNOWN, `QUERY_PARK_STA` |
| inductance_coil.py / probe_inductance_coil.py | 433 / 2023 | Per-tool inductive nozzle probe; `PROBE_XYZ_OFFSET_CALIBRATE`; `ExtruderOffsetCalibration` (EXTRUDER_OFFSET_ACTION_* state machine) |
| extruder_config_bak.py | 292 | Persists `xy_park_position`, `y_idle_position`, `base_position` per extruder in JSON (keyed by section name, generic) |
| extruder_calibration.py | 405 | Park-point calibration helpers |
| flow_calibrator.py | 1364 | Pressure-advance (K) auto-calibration with inductive sensor |
| print_task_config.py | 1471 | Per-print filament/extruder mapping, `extruder_map_table`, persisted task config |
| filament_feed.py | 2008 | Feeder modules (2 channels each) |
| filament_detect.py / filament_protocol.py / fm175xx_reader.py | 287 / 471 / 1061 | RFID filament tags |
| filament_entangle_detect.py, filament_parameters.py, filament_feed_fac_test.py | 293 / 1703 / 302 | Filament features |
| homing_precise_corexy.py / homing_xyz_override.py | 598 / 481 | Precise sensorless CoreXY homing, homing override with dock-aware safe Y |
| machine_state_manager.py | 444 | Main state + action codes reported to UI |
| power_loss_check.py, defect_detection.py, purifier*.py, timelapse.py, mqtt.py, jsonrpc.py, sc7a20.py, error_mcu.py, garbage_collection.py | - | Misc product features |

Also new in `klippy/`: `exception_manager.py` (374), `coded_exception.py`, `printer_device_scan.py`, `asyncfilereader.py`, `queuefile.py`.

### Heavily modified upstream files
- `klippy/kinematics/extruder.py` (2232 lines vs ~350 upstream) - the whole tool-changer implementation lives here.
- `klippy/toolhead.py` - logical/physical extruder counts (`:247-248`), `SWITCH_OF_EXTENDED_EXTRUDER` (`:320`, `:694-713`), auto-activate detected tool after start (`:642-658`), grab-complete flag (`:299`, `:787-790`).
- `klippy/mcu.py` (coded MCU-loss errors, `:1051-1079`), `klippy/klippy.py` (connect errors, USB hub check `:435-457`, `:551`), `klippy/serialhdl.py` (`:323`), `heaters.py`, `virtual_sdcard.py`, `print_stats.py`, `bed_mesh.py`, `input_shaper.py`, `filament_switch_sensor.py`.

### MCU firmware (`src/`)
- `src/stm32/at32f403a.c/.h` (main board), `src/stm32/at32f415rc.c/.h` (toolhead), `src/stm32/inductance_coil.c/.h`, `src/stm32/power_loss_check.c`, `src/stm32/n32g45x_adc.c`, `src/sensor_sc7a20.c`, `src/hc32f460/`; `src/endstop.c` has `CONFIG_MACH_AT32F4x` hooks for the inductance probe (`:15-16, 38, 61, 133`); `src/stm32/Kconfig:114-121, 156, 203-204, 223-224` add `MACH_AT32F415` / `MACH_AT32F403A`.

---

## 2. Tool-change implementation

### Configuration per tool (`lava/printer.cfg`, blocks e0 `:665-825`, e1 `:830-964`, e2 `:969-1103`, e3 `:1107-1241`)
- `[extruderN]`: step/dir/enable `eN:PA8/PA9/PB2`, heater `eN:PB5`, sensor `eN:PA2`, `xy_park_position`, `y_idle_position: 250`, `extruder_grab_dir` (True for e0, False for e1-e3), `horizontal_move_x: 10`, `retract_x_dist: 1.5`, `fast_move_speed: 400`, `slow_move_speed: 60`, `grab_speed: 10`, `switch_accel: 5000`, `insertion_buffer_dist: 5`, `base_position`.
- Dock coordinates: e0 `35.0,332.2`; e1 `102.7,332.2`; e2 `170.2,332.2`; e3 `237.7,332.2` (pitch ~67.5 mm, single row at the rear).
- `[tmc2209]` (uart `eN:PA15`), `[park_detector]` (park pin on **main MCU**: PB0/PC4/PC5/PB1; active pin `eN:PB1`; grab_valid `eN:PA3`), print fan (`[fan]` only for e0, `fan_generic eN_fan` for others), `[heater_fan eN_nozzle_fan]`, `eN_heat_sw`, `[filament_motion_sensor eN_filament]`, `[filament_entangle_detect]`, `[inductance_coil extruderN]` (`eN:PA0`), `[power_loss_check eN]`. Accelerometer only on e0.

### Python (`klippy/kinematics/extruder.py`)
- Exceptions `ExtruderParkAction`, `ExtruderUnknownParkStatus`, `ExtruderPickAbnormal` (`:10-17`).
- `ExtruderSwitchRecorder` (`:38-259`): switch counters, `extruder_switch_recorder.json`, `GET/RESET_EXTRUDER_SWITCH_RECORDER`, `RESET_EXTRUDER_MAINTENANCE_COUNT` (thresholds 25100/tool, 100000 total).
- `PrinterExtruder.__init__`: reads park/idle (JSON backup overrides cfg, `:519-551`), registers `T%d`, `PARK_/PICK_/MOVE_TO_XY_IDLE_POSITION_<NAME>` (`:544-550`), base_position (`:561-572`). Extruder 0 only registers M104/M109, park-point manual calibration, webhooks, `GET_EXTRUDER_ACTIVATE_INFO` (`:595-610`). Mux commands `ACTIVATE_EXTRUDER`, `SET_EXTRUDER_BASE_POSITION`, `SET_EXTRUDER_PARK_POSITION`, `MOVE_TO_PARK_CALIBRATION_POINT`, `VERIFY_PARK_POSITION`, `SET_NOZZLE_DIAMETER/PROPERTIES`, `INNER_APPLY_FLOW_K` (`:611-629`).
- Offsets: `get_center_base_position` = bounding-box centre of all tools' `base_position`; tool offset = base - centre, applied with `SET_GCODE_OFFSET ... MOVE=0` on switch (`:704-728`, `:1762-1818`). Generic in N.
- Detection: `get_extruder_activate_status` -> `[[name, code], states, pins]`, code 0 = exactly one active, 1 = all parked, 2 = unknown (`:830-853`).
- `Tn` -> `cmd_SWITCH_EXTRUDER_ADVANCED` (`:1330-1344`), maps index through `print_task_config.extruder_map_table` unless `A0`.
- `cmd_SWITCH_EXTRUDER` (`:1345-1409`): retry wrapper (`retry_switch_limit` 3), forced park on pogo-pin errors, marks XY unhomed on failure.
- `_cmd_SWITCH_EXTRUDER` (`:1411-1818`) state machine:
  1. home XY if needed; poll activation status (10 x 0.2 s);
  2. turn off print fan / set fan PWM for grip detection; save gcode state; `set_accel(switch_accel)`;
  3. **Park current tool** (`:1555-1624`): if Y > y_idle -> Y to y_idle, X to `park_x +/- (horizontal_move_x - retract_x_dist)` (with 0.5 mm approach), else X first then Y to y_idle; Y fast to `max(park_y - insertion_buffer, y_idle)`; Y slow to `park_y`; X slow to `park_x` (unlocks tool); Y back to y_idle; verify PARKED (10 retries), error codes `0002-0523-<tool>-0020/0042/0043/0044` decoded from pin pattern (`park,active,grab_valid` = FTT/FFT/TTT...).
  4. **Pick new tool** (`:1633-1751`): pre-check PARKED (`-0021`), Y to y_idle, X to `park_x`, Y fast/slow into dock, X to `park_x +/- horizontal_move_x` at `grab_speed` (lock), retract `retract_x_dist`, Y to y_idle, wait ~2.5 s for fan check, verify ACTIVATE for this tool (10 retries).
  5. Restore gcode state, `toolhead.set_extruder`, event `extruder:activate_extruder`, bind probe/fan, apply offset.
- Error analysis `analyze_switch_extruder_error` (`:913-1039`) - hardcoded to 4 (see table).
- Calibration: `MOVE_TO_XY_IDLE_POSITION` (`:1820-1864`, special-case `x -= 2` for extruder 0), `MOVE_TO_PARK_CALIBRATION_POINT` (`:2035-2079`, default `move_calibration_y = 320`, overridable by macro `_MOVE_TO_<NAME>_PARK_CALIBRATION_POINT`), `VERIFY_PARK_POSITION` (`:2081-2140`).
- `add_printer_objects` (`:2200-2232`): loops `range(99)`, requires all-or-none tools to have `park_detector` and `xy_park_position`, registers `extruder_list`.

### Persistence
- `extruder_config_bak.py:183-242`: JSON backup (`extruder_config.json`, `extruder_base_position.json`) is written **only if the files do not exist** (`:188-189`). New tools e4-e7 will not be added to an existing backup at boot; `get_extruder_config` returns `None` for unknown names (`:78-79`) so they fall back to printer.cfg values - works, but calibration writes will add them later via `update_extruder_config`.

---

## 3. Hardcoded "4 toolheads" assumptions

| # | Location | What is hardcoded | Change needed for 8 tools |
|---|---|---|---|
| 1 | `lava/printer.cfg:107-115` | `max_physical_extruder_num: 4` (`max_logical_extruder_num: 32`) | Set 8 |
| 2 | `lava/printer.cfg:15-28` | `[mcu e0..e3]` by-path serials on hub ports 1.1-1.4 | Add `[mcu e4..e7]` with new by-path (needs extra USB hub) |
| 3 | `lava/printer.cfg:665-1241` | Four per-tool blocks (extruder, tmc2209, park_detector, fans, heat_sw, motion sensor, entangle detect, inductance_coil, power_loss_check) | Duplicate for extruder4..7 with `e4..e7:` pins, new dock coords, new main-MCU park pins |
| 4 | `lava/printer.cfg` park_detector | Park pins PB0/PC4/PC5/PB1 on main MCU ADC | 4 more ADC-capable pins (spare main-MCU pins, an expansion `[mcu]`, or move sensing to a toolhead/dock MCU) |
| 5 | `lava/printer.cfg:314-316` | `[heater_fan power_fan] heater: extruder, extruder1, extruder2, extruder3` | Add extruder4..7 |
| 6 | `lava/printer.cfg:44-59` | `[fm175xx_reader]` 2 readers x 2 channels | Only 4 RFID slots; tools 5-8 without RFID unless new readers |
| 7 | `lava/printer.cfg:1245-1326` | `[filament_feed left/right]` (2 ch each), `_FILAMENT_FEED_VARIABLE module_sequence 'left','left','right','right'`, `channel_sequence 1,0,0,1` | Add modules/sequences or mark tools 5-8 as manual-feed |
| 8 | `klippy/extras/print_task_config.py:8-9` | `PHYSICAL_EXTRUDER_NUM = 4` module constant (not read from config); sizes arrays `:26-61`, `:92-98`, length validation `:199-214`, `:426-428`, range checks `:302`, `:315`, `:374`, `:553-554`, `:604-605`, `:750-753`, `:794-797`, `:831`, `:854`, `:918`, `:1144-1148`, `:1175`, `:1193-1199` etc. | Read from `printer.max_physical_extruder_num`; persisted task-config JSON with length 4 will fail validation and be reset (acceptable, or add migration) |
| 9 | `klippy/extras/print_task_config.py:511-525` | Loops `PHYSICAL_EXTRUDER_NUM`, looks up `filament_motion_sensor e{ch}_filament` and feeder `extruder{ch}` | Generic once constant changes; feeder lookup returns None for 5-8 (OK) |
| 10 | `klippy/extras/print_stats.py:9-10` | `LOGICAL 32`, `PHYSICAL 4` defaults (overridden from toolhead `:57-63`) | Change default or rely on override |
| 11 | `klippy/kinematics/extruder.py:936-939` | `MAX_EXTRUDERS = 4`; >4 returns `None` (no error analysis) | Use `len(extruder_list)` |
| 12 | `klippy/kinematics/extruder.py:964-976`, `:1004-1020` | `extruder_combinations` (11 combos of 0-3), `unknown_combinations` (15 combos) -> numeric codes | Replace with bitmask encoding; coordinate new codes with UI/app error tables |
| 13 | `klippy/kinematics/extruder.py:1458`, `:1725` | Error code ranges `activated_code + 6 < 18`, `23 + activated_code < 35` (35 = fallback) | Redefine code space (codes are part of the UI error catalogue) |
| 14 | `klippy/kinematics/extruder.py:1584`, `:1679`, `:1567`, `:1662`, `:1852`, `:2074-2077` | Dock assumed at Y > y_idle (`max(...)`, `pos[1] > y_idle`) | Direction-aware logic for a front/other row (see section 6) |
| 15 | `klippy/kinematics/extruder.py:2054` | `move_calibration_y = 320` default | Per-tool default (or define `_MOVE_TO_EXTRUDERn_PARK_CALIBRATION_POINT` macros) |
| 16 | `klippy/kinematics/extruder.py:1835-1836` | `if name == "extruder": x -= 2` | Not count-related, but per-tool quirk to keep in mind |
| 17 | `klippy/mcu.py:1051-1076` | `{'e0':2..'e3':5}` index map, `index in (2,3,4,5)`, loop `['e0'..'e3']`, `checked == 4` ("All extruder MCUs lost") | Generate from configured `mcu eN` list; e4-e7 currently map to 255 (still shuts down, generic code) |
| 18 | `klippy/klippy.py:435-457`, `:551` | `mcu_index_manager` e0-e3; expects `hub_count >= 2` "QinHeng Electronics USB HUB" | Extend list; adjust hub count check if a third hub is added |
| 19 | `klippy/serialhdl.py:323` | `{'mcu':0,'e0':1..'e3':4}` | Extend |
| 20 | `klippy/printer_device_scan.py:7-8`, `:21`, `:50` | `CFG_MCU_SECTION_NAME` E0-E3, 6-entry index map, `range(4)` | Extend (helper only; scan function not used at runtime, only `run_shell_command`) |
| 21 | `klippy/extras/flow_calibrator.py:163-164`, `:311` | `DEFAULT_K`, `DEFAULT_CALI_STATE` dicts for extruder..extruder3; JSON validation requires exactly those keys | Build dicts from `extruder_list`; otherwise KeyError for extruder4+ |
| 22 | `klippy/extras/probe_inductance_coil.py:448`, `:826` | name->index dict extruder..extruder3 (default 0) | Use `extruder_index` |
| 23 | `klippy/extras/probe_inductance_coil.py:528` | Log line break after `extruder3` | Cosmetic |
| 24 | `klippy/extras/probe_inductance_coil.py:1258-1286` | `extruder_mapping` T0-T3, `manual_clean_nozzle_status`, `last_xyz_result` for 4 tools | Generate from `extruder_list`; otherwise `TOOL_ID=T4..T7` rejected as unsupported |
| 25 | `klippy/extras/probe_inductance_coil.py:1608`, `:1618` | `range(4)` for `T{n}_TEMP` params | `range(N)` |
| 26 | `klippy/extras/probe_inductance_coil.py:1787-1799` | `EXTRUDER..EXTRUDER3_TARGET`, `'all'` list | Generate |
| 27 | `klippy/extras/machine_state_manager.py:47-54`, `:62-65` | Action codes MANUAL_CLEAN_EXTRUDER..3 = 192-195, XYZ_OFFSET_PROBE 196-199, FLOW_CALIBRATING 320-323 (200/201 already taken) | Allocate new codes for extruder4..7 (e.g. 202-209, 324-327); UI must know them. `SET_ACTION_CODE ACTION=MANUAL_CLEAN_EXTRUDER4` would fail otherwise |
| 28 | `klippy/extras/filament_feed.py:5` | `FEED_CHANNEL_NUMS = 2` per module | OK per module; more modules needed for more tools |
| 29 | `klippy/extras/fm175xx_reader.py:7`, `filament_detect.py:15` | `FM175XX_CHANNEL_NUMS = 4`, `FILAMENT_DT_CHANNEL_NUMS = 4` | Increase only if more readers are added |
| 30 | `lava/fluidd.cfg:67-177` | `[gcode_macro T4]`..`T31` -> `SWITCH_OF_EXTENDED_EXTRUDER INDEX=n` | Remove T4-T7 (name collision with native commands; also `toolhead.py:696` rejects index < max_physical) |
| 31 | `lava/fluidd.cfg:195-202`, `:350-353`, `:394-403`, `:425-428`, `:436-439`, `:548-566`, `:1657-1704` | PRINT_START / INNER_PAUSE / INNER_RESUME / AUTO_FEEDING_BATCH hardcode extruder0-3 temps and T0-T3 | Loop over `max_physical_extruder_num` |
| 32 | `lava/fluidd.cfg:918-1015` | SM_PRINT_START_LINE if-chain for map values 0-3; `SM_PRINT_START_LINE_EXTRUDER_0..3` purge lines at X 10/60/110/160, Y3 | Add 4 more purge-line positions (or second Y row) |
| 33 | `lava/fluidd.cfg:179-185`, `:1018+`, `:1109+` | Discard/cut/wipe macros relative to each tool's idle position (Y_OFFSET=+50.5, i.e. towards the rear dock) with extruder-0 special case | Front-row tools need mirrored offsets and their own purge/cut hardware |
| 34 | `lava/xyz_offset_calibration.cfg:60-78`, `:82-389`, `:342-347`, `:405-417` | PREHEAT dict/loop T0-T3, per-tool HEAT/AUTO_CLEAN/MANUAL_CLEAN/WAIT_COOL/PROBE_CALIBRATE macros T0-T3, CALIBRATE_ALL lists | Add T4-T7 variants/loops |

Not tool-count related (checked and excluded): `exclude_object.py:155, 205` `range(4)` = XYZE axes; `flow_calibrator.py:958` `range(4)` = iteration count; `auto_screws_tilt_adjust` `range(4)` = screws.

---

## 4. Toolhead MCU communication and limits

- Main MCU: AT32F403A (`lava/at32f403a_config`: `CONFIG_MCU="stm32f103xe"`, 240 MHz, `CONFIG_SERIAL`, 921600 baud) on `/dev/ttyS6` (`printer.cfg:9-12`). Initial pins include `PE15` (global power enable `printer.cfg:281`) and feeder motor pins PD4-PD7.
- Toolhead MCU: AT32F415 (`lava/at32f415_config`: `CONFIG_MCU="stm32f105xc"`, 144 MHz, `CONFIG_USBSERIAL=y`, VID:PID 1d50:614e, serial = chip ID, flash at 0x8000000 i.e. no bootloader offset, initial pins `PB2,!PB5,PB0,!PB3` = stepper enable off, heater off, fan, ...). CAN frequency is set but **CAN is not used**.
- Each toolhead is a separate Klipper `[mcu eN]` over USB CDC; host identifies them **by USB port path**, so the physical dock/pogo-pin position determines identity, not a firmware ID. All toolheads run the same binary.
- Topology: `platform-xhci-hcd.0.auto-usb-0:1.{1..4}:1.0` -> one 4-port hub on root port 1. `klippy.py:443-450` expects two "QinHeng Electronics USB HUB" devices. For e4-e7: cascade another hub (e.g. on a free port), paths become `...usb-0:1.x.y:1.0`; update `[mcu eN] serial`.
- Load: each toolhead MCU adds a clocksync + serial queue on the host; 8 USB-FS MCUs is well within Klipper practice (multi-MCU setups with 8+ boards exist), but host CPU (the U1 SoC) and the 921600 main UART are unchanged. Motion of extruder steppers is on each toolhead MCU; only one is moving at a time.
- Per-tool signals over pogo pins: heater, thermistor, extruder stepper (TMC2209 UART), fans + tach, inductance coil, active/grab_valid Hall sensors, accelerometer (e0 only). Dock "parked" signal is on the **main** MCU (ADC button) - 4 pins.
- MCU-loss handling: `mcu.py:1046-1079` raises `0003-0522-<index>-0008`; unknown names get index 255 (still safe shutdown).

---

## 5. Kinematics and dock/collision constraints

- CoreXY, `max_velocity 500`, `max_accel 20000` (`printer.cfg:107-115`); X 0..271, Y 0..335, Z 0(-6)..275 (Z = bed, carriage Z fixed) (`:117-171`). Bed mesh 3..267 x 3..267 (`:286-296`).
- Homing: sensorless TMC2240 X/Y to **min** (position_endstop 0, i.e. front-left), `[homing_precise_corexy]` (`:305`), `[homing_xyz_override]` `home_xy_position: 10,10` (front-left) (`:510-524`).
- Safe zone: `homing_xyz_override.py:20` `safe_move_y_pos` default 250; before XY moves it retreats to Y=250 if beyond (`:228-233`). Combined with `y_idle_position: 250` this defines "Y > 250 = dock zone" (docks at Y=332.2). No explicit collision model; safety is purely the Y-first/X-second move ordering in `_cmd_SWITCH_EXTRUDER`.
- Dock geometry: single row, Y=332.2, X pitch ~67.5 mm (35.0/102.7/170.2/237.7). Tool is locked/unlocked by an X slide of `horizontal_move_x` (10 mm) after inserting in +Y; `extruder_grab_dir` chooses the slide direction (e0 opposite to e1-e3 because of the left wall).
- Implications for a second row:
  - **Rear (behind current row):** impossible without extending Y travel beyond 335 and passing through/around row 1 (would need staggered X positions; with 67.5 mm pitch and 271 mm X there is no gap).
  - **Front row (Y ~ 0):** feasible in software but costs ~80 mm of Y print depth (or a frame extension with negative `position_min`), and conflicts with: Y homing to 0 (sensorless crash into docks), `home_xy_position 10,10`, purge lines at Y3 (`fluidd.cfg:937-1015`), manual-clean position X135 Y5 (`xyz_offset_calibration.cfg:253`), bed mesh min Y 3. Tools would enter the dock in -Y, i.e. the tool must have dock features on its front face and the carriage coupling must work mirrored (mechanical question).
  - **Side docks:** X travel 0..271 already used; approach would be along X, which conflicts with the X-slide lock mechanism - largest change.

---

## 6. Feasibility and recommended approach

**Config-only? No.** Config can add the tool blocks, MCUs and dock coordinates, but a working 8-tool system needs code changes (table rows 8, 11-14, 17-19, 21-27) and macro rewrites (rows 30-34). Firmware for the toolhead MCUs needs no change.

### Concrete approach
1. **Config (`lava/printer.cfg`)**
   - `max_physical_extruder_num: 8`.
   - `[mcu e4]..[mcu e7]` on the new hub ports.
   - `[extruder4]..[extruder7]` (and all companion sections) copied from e1-e3 with `e4:`..`e7:` pin prefixes, new `xy_park_position`, `y_idle_position`, `extruder_grab_dir`, and new park-detector pins.
   - Add extruder4-7 to `[heater_fan power_fan]`. Leave feeders/RFID at 4 or add hardware.
2. **Generalise counts (Python)**
   - `print_task_config.py`: replace `PHYSICAL_EXTRUDER_NUM` constant with value read from `[printer]` at init (lazy, since it is used in module-level dict templates -> build templates in `__init__`). Accept/migrate 4-length persisted arrays.
   - `extruder.py`: `MAX_EXTRUDERS = len(extruder_list)`; replace combination dicts with bitmask (`sum(1<<i)`) or "first offending index" codes; agree on new error-code ranges.
   - `mcu.py`, `klippy.py`, `serialhdl.py`, `printer_device_scan.py`: derive e-MCU list from `printer.lookup_objects('mcu')` / names matching `e\d+`.
   - `flow_calibrator.py`, `probe_inductance_coil.py`: build per-extruder dicts from `extruder_list`; `range(N)`.
   - `machine_state_manager.py`: add action codes for extruder4-7.
3. **Direction-aware dock motion (`extruder.py`)**
   - New per-tool option, e.g. `dock_side: rear|front` (or derive `sign = 1 if park_y > y_idle else -1`).
   - Replace `max(park_y - buffer, y_idle)` with `park_y - sign*buffer` clamped towards y_idle, and `pos[1] > y_idle` with `sign*(pos[1] - y_idle) > 0` in park (`:1567-1593`), pick (`:1662-1700`), `MOVE_TO_XY_IDLE_POSITION` (`:1852`), `MOVE_TO_PARK_CALIBRATION_POINT` (`:2054-2079`), and `VERIFY_PARK_POSITION`.
   - Important: when switching between a rear tool and a front tool, the carriage must first go to the current tool's y_idle, then travel to the other row's y_idle; current code goes directly X then Y which is fine only within one row. Add an explicit "travel via neutral Y band" step.
   - `homing_xyz_override.py`: add `safe_move_y_min` mirror of `safe_move_y_pos`; move `home_xy_position` and Y homing away from the front dock band (or home Y to max).
4. **Macros**: remove `T4..T7` from `fluidd.cfg` (keep T8..T31 extended), rewrite PRINT_START/PAUSE/RESUME/AUTO_FEEDING_BATCH/SM_PRINT_START_LINE loops over `max_physical_extruder_num`, add purge-line positions, add T4-T7 calibration macros in `xyz_offset_calibration.cfg`, define `_MOVE_TO_EXTRUDERn_PARK_CALIBRATION_POINT` for front docks, mirrored discard/cut/wipe macros for front tools.
5. **Bring-up path**: start with the Extended-Firmware toolhead MCU simulator (`faulty_toolhead*_mcu.cfg`) to boot an 8-extruder config without hardware, then validate motion with real docks at low speed (`fast_move_speed`, `switch_accel` reduced).

### Alternative (no new physical tools)
Keep 4 physical tools and use the existing logical mapping (`T4..T31` -> `SWITCH_OF_EXTENDED_EXTRUDER` + `extruder_map_table`) with manual tool/filament swaps. This is purely a workflow, not 8 concurrent tools.

### Out of firmware scope (but will break)
Touch-screen UI / Moonraker / cloud app and the Snapmaker Orca slicer profiles very likely assume 4 tools (status arrays, error-code catalogue, action codes, filament slots). These need separate verification.

---

## Open questions

1. Mechanical: where can a second dock row physically go? Front row costs ~80 mm Y print depth or a frame extension; can the toolhead/carriage coupling be engaged from the opposite (-Y) direction?
2. Are there 4 spare ADC-capable pins on the AT32F403A main board (or a free connector) for the extra dock "parked" sensors, or must an extra Klipper MCU be added for dock sensing?
3. USB: does the U1 SoC have a spare USB port / can the second QinHeng hub accept a cascaded hub, and can the 5 V rail supply 4 more toolheads (heaters are 24 V via pogo pins - is the power path per dock sized on the main board)?
4. Toolhead power and heater switching: is `eN_heat_sw` / toolhead power gated from the main board per dock (main-MCU pins), which would require more main-board outputs?
5. Is the print fan / grip-detection fan-PWM trick (`switch_extruder_ctr_fan_pwm`) dependent on any main-board signal that is per-dock?
6. Will the closed-source parts (touchscreen GUI, Snapmaker cloud/app, possibly Moonraker extensions) accept `max_physical_extruder_num: 8`, 8-length arrays in `print_task_config`, new action codes and new error codes? Is the GUI rebuildable?
7. Does the slicer emit `T4..T7` as physical tools for an 8-tool profile, or will it use the logical mapping (A parameter) - and does the firmware's `extruder_map_table` handling need changes for that?
8. Purge/cut/wipe hardware: each rear dock has a discard/cut area at y_idle+50.5; where would front-row tools purge and cut filament?
9. Homing: can Y be re-homed to max (rear) safely with rear docks, or does the precise CoreXY homing (`homing_precise_corexy.py`) rely on front-left homing?
10. Factory calibration fixtures: XYZ offset calibration probes a fixed fixture at X13 / Y234.5 (`xyz_offset_calibration.cfg:403`); is it reachable by front-row tools given their different dock/approach?
