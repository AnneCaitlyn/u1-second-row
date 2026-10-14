# 01 - Snapmaker U1 hardware, mechanics and electronics (second-row toolhead research)

Scope: the physical and electrical facts about the U1 that matter for adding a second row of docked toolheads (4 more heads, 8 in total).

Source limitation: the Snapmaker wiki (https://wiki.snapmaker.com/en/home) could not be fetched in this session because the WebFetch calls were declined. Everything below therefore comes from the local read-only clones under `C:\Users\N\u1-second-row\refs\`, mainly:

- The stock U1 Klipper config `C:\Users\N\u1-second-row\refs\u1-klipper\lava\printer.cfg` (1365 lines).
- The U1 Klipper fork sources.
- The SnapmakerU1-Extended-Firmware docs and overlays.
- The OrcaSlicer U1 machine profile.

Values that only the wiki or a teardown would give are listed under "Open questions": PSU wattage, frame dimensions, board photos and connector pinouts.

Abbreviations: `refs\` = `C:\Users\N\u1-second-row\refs\`; `cfg` = `refs\u1-klipper\lava\printer.cfg`.

---

## Key findings

1. **Docks: one fixed rear row with no room for a second.**
   - All 4 docks are at the same Y: `xy_park_position` 35.0 / 102.7 / 170.2 / 237.7, all at Y = 332.2 (cfg L694, L859, L998, L1136). That gives a pitch of 67.5 mm.
   - Y `position_max` is 335 (cfg L149), so only about 2.8 mm of Y travel is left past the docks.
   - X travel is 0-271 (cfg L128), and the 4 docks already span it.
   - The machine is CoreXY with a bed that moves in Z (cfg L107-115, L160-180). The docks sit in the fixed gantry plane, so you cannot stack a row "above" or "below" them.
   - Conclusion: a second row needs one of three things: more Y travel (a frame or gantry change), docks in front at Y < 0, or a moving dock carrier that brings parked heads into the 4 reachable positions.
2. **Docking is purely XY.**
   - The head approaches in +Y, then a 10 mm X slide (`horizontal_move_x`) latches or unlatches it. Nothing extra is actuated (`klippy\kinematics\extruder.py` L1555-1700).
   - So any new dock just needs (a) a reachable XY pose, (b) about 10 mm of free X on the grab side, and (c) about 5 mm of slow Y approach.
3. **Each toolhead is its own USB Klipper MCU.**
   - The head MCU is an AT32F415 at 144 MHz (`refs\u1-klipper\lava\at32f415_config`), wired as USB serial through a 4-port hub on the SoC xHCI. The by-path ports are `...usb-0:1.1` to `1.4` (cfg L15-28).
   - The hub is full: 4 more heads need another USB hub or port.
   - Each head carries its own hotend heater and NTC, extruder TMC2209, part fan, hotend fan, filament motion sensor, inductive nozzle probe, Hall sensors (active and grab-valid) and power-loss input. Only T0 also has an accelerometer.
4. **Dock occupancy is sensed on the mainboard.**
   - Each dock's park sensor is an ADC input on the main MCU: PB0 / PC4 / PC5 / PB1 (`[park_detector ...]`, cfg L720, L885, L1024, L1162).
   - Only about 3 main-MCU ADC-capable pins look unused in the config (PA4, PA5, PC3), and it is unknown whether they are broken out.
   - 4 more dock sensors would most likely come from an extra MCU. `park_detector` accepts digital buttons as well as ADC (`klippy\extras\park_detector.py`).
5. **Main MCU and CAN.**
   - The main MCU is an AT32F403A at 240 MHz, linked to the RK3562 host over UART `/dev/ttyS6` at 921600 baud (cfg L9-13; `lava\at32f403a_config`).
   - Its firmware is built as USB-to-CAN bridge plus serial, with CAN on PB5/PB6 at 500 kbit/s. That is a latent CAN option, but whether a CAN connector exists on the board is unknown.
6. **Filament system is sized for exactly 4 everywhere.**
   - Feed: 2 feed modules (left and right). Each has 1 DC motor and 2 channels selected by a direction clutch, and each module uses about 13 main-MCU pins (cfg L1245-1326).
   - NFC: 2 FM17580 readers on SoC SPI2 with 2 antennas each (cfg L44-61).
   - Firmware constants are hard-coded to 4: `FM175XX_CHANNEL_NUMS = 4`, `FILAMENT_DT_CHANNEL_NUMS = 4`, `PHYSICAL_EXTRUDER_NUM = 4`, `max_physical_extruder_num: 4`.
7. **Power: unknown PSU rating, with a firmware budget.**
   - Klipper limits heating to 2 extruders at once (`MAX_HEATING_EXTRUDERS = 2`, `klippy\extras\heaters.py` L500).
   - Parked heads are held at a lower power fraction (`idle_hold_max_power: 0.5`).
   - The mainboard measures total current through a 0.01 Ohm shunt (`[adc_current_sensor I_AD]`, cfg L322).
   - This budget scheme carries over to 8 heads, but PSU headroom for 8 idle-warm heads is unverified.
8. **Thermal limit on the host.**
   - The community reports the RK3562 throttling at about 85 C and the mainboard overheating. Cooling mods exist (Extended Firmware `docs\panda_breath.md` L37-52).
   - 4 more USB MCUs and a hub add host load and heat.
9. **Prior art.**
   - Nothing found in local sources that physically adds toolheads to a U1.
   - Related community work:
     - A toolhead-MCU simulator for running with a dead or missing head.
     - Logical tools T4-T31 mapped onto the 4 physical heads (`SWITCH_OF_EXTENDED_EXTRUDER`).
     - External RFID readers (ESP32 + PN532).
     - Relocated feeders (BIQU PopStation mini, 2000 mm preload).
     - Dock-speed tweaks.

---

## 1. Physical layout, docks, pick/park motion, kinematics

### 1.1 Kinematics and travel
| Item | Value | Source |
|---|---|---|
| Kinematics | `corexy`, max_velocity 500, max_accel 20000, max_z_velocity 30 | cfg L107-115 |
| Logical / physical extruders | `max_logical_extruder_num: 32`, `max_physical_extruder_num: 4` | cfg L113-115 |
| X | rotation_distance 40, microsteps 64, `position_max: 271`, sensorless homing (TMC2240, SPI), run_current 1.2 A | cfg L117-147 |
| Y | `position_max: 335`, TMC2240, 1.2 A | cfg L149-158 area |
| Z (bed) | rotation_distance 8, gear ratio 3:1, position_max 275, min -6, TMC2209 0.85 A | cfg L160-207 |
| Homing XY position | 10,10 (`homing_xyz_override`) | cfg L510-517 |
| Input shaper | mzv, X 54 Hz, Y 47.5 Hz; accel chip `e0_accelerometer` (on T0 only) | cfg L77-97 |
| Bed mesh | 3,3 to 267,267 | cfg L286-303 |
| Bed screws | (15,15) (255,15) (255,255) (15,255) | cfg L353-368 |
| Slicer printable area | X 0.5-270.5, Y 1-271, height 270.05 | `refs\OrcaSlicer\resources\profiles\Snapmaker\machine\Snapmaker U1 (0.4 nozzle).json` |
| Slicer clearance | `extruder_clearance_radius` 72.5, `extruder_clearance_height_to_rod` 27.5, `machine_tool_change_time` 5 s | same file |

Interpretation:

- The print area is about 270 x 270 mm. The Y axis continues to 335, so roughly 64 mm behind the print area is a "service zone" where the gantry visits the docks and the purge/wipe positions.
- The bed moves in Z, so toolheads and docks always share the gantry's single XY plane.

### 1.2 Docks
| Tool | Klipper section | `xy_park_position` | `extruder_grab_dir` | Park sensor (main MCU) | Source |
|---|---|---|---|---|---|
| T0 | `[extruder]` | 35.0, 332.2 | True | PB0 | cfg L665-720 |
| T1 | `[extruder1]` | 102.7, 332.2 | False | PC4 | cfg L830-885 |
| T2 | `[extruder2]` | 170.2, 332.2 | False | PC5 | cfg L969-1024 |
| T3 | `[extruder3]` | 237.7, 332.2 | False | PB1 | cfg L1107-1162 |

Common toolchange parameters, set per extruder section:

- `y_idle_position: 250`
- `horizontal_move_x: 10`
- `retract_x_dist: 1.5`
- `fast_move_speed: 400`
- `slow_move_speed: 60`
- `grab_speed: 10`
- `switch_accel: 5000`
- `insertion_buffer_dist: 5`

T0 has the opposite grab direction to the others because it sits at the left edge (X = 35). There is not enough X travel to its left for a slide in the same direction as the other heads.

### 1.3 Park sequence (`refs\u1-klipper\klippy\kinematics\extruder.py` L1555-1627)
1. Move to Y = `y_idle_position` (250).
2. Move in X to `park_x ± (horizontal_move_x - retract_x_dist)`, which is the latch-open offset.
3. Move fast in +Y to `park_y - insertion_buffer_dist` (327.2), then slowly to `park_y` (332.2).
4. Slide in X back to `park_x`, which releases the latch so the head stays in the dock.
5. Return to Y idle.
6. Verify with `get_extruder_activate_status`: the dock park sensor must read PARKED and no head may read ACTIVATE. It retries up to 10 times and reports Hall state codes such as FTT, FFF or TTT.

### 1.4 Pick sequence (extruder.py L1633-1700)
1. At Y idle, move to X = `park_x`.
2. Move fast in +Y to `park_y - 5`, then slowly to `park_y`.
3. Slide ±10 mm in X at `grab_speed`, which latches the head onto the carriage. Then back off 1.5 mm.
4. Return to Y idle.
5. Verify that exactly one extruder is ACTIVATE and all others are PARKED (extruder.py L830-853).

### 1.5 Detection logic (`refs\u1-klipper\klippy\extras\park_detector.py`, 96 lines)
- There are three inputs per tool:
  - `park_pin`: in the dock, on the main MCU.
  - `active_pin`: a Hall sensor on the toolhead MCU (eN:PB1).
  - `grab_valid_pin`: a Hall sensor on the toolhead MCU (eN:PA3).
- Each input may be an ADC button (`analog_range`) or a plain digital button.
- Resulting states are ACTIVATE (active and not parked), PARKED, or UNKNOWN. `QUERY_PARK_STA` reports them.
- extruder.py L497-551 binds the detector and creates `PARK_<NAME>`, `PICK_<NAME>` and `MOVE_TO_XY_IDLE_POSITION_<NAME>` for every extruder section.
- `add_printer_objects` (extruder.py L2200-2232) iterates `extruder`, `extruder1` and so on, up to 99 sections, so the loader is not capped at 4. All extruders must consistently define (or all omit) `park_detector` and `xy_park_position`.

### 1.6 Other fixed XY positions in the rear and service zone
- The purge position is the dock X at Y idle + 50.5, i.e. about Y 300.5 in front of each dock (`MOVE_TO_DISCARD_FILAMENT_POSITION`, `refs\u1-klipper\lava\fluidd.cfg` L179-185).
- Per-dock cutter, wipe and purge geometry therefore sits between the print area and the dock row. A rear second row would have to clear this hardware, or the Y travel would have to extend past it.
- Prime lines are per extruder at X10/60/110/160, Y3 (fluidd.cfg). `INNER_DETECT_NOZZLE` is at X195 Y16.
- XYZ offset calibration probes a feature at X13, Y233-234.5 (`refs\u1-klipper\lava\xyz_offset_calibration.cfg` L45-57, L403). The macros are hard-coded for T0..T3 (L60-389, L405-417).

### 1.7 Space for a second row: assessment
- **Behind the current docks:** not possible with stock travel, because 335 - 332.2 = 2.8 mm. It would need a longer Y axis: frame or rear panel, longer Y belts and rails, a raised `position_max`, a re-tuned input shaper and a new enclosure. Physical depth behind the docks is unknown.
- **In front, at Y < 0:** stock Y min is 0 (homing at 10,10). Front docks would hang over the front edge of the bed and the door area. This needs negative Y travel, and the bed moving in Z would need clearance under the docks at high Z.
- **Interleaved in X between existing docks:** not possible. The pitch is 67.5 mm and each pick/park needs a 10 mm X slide plus head width. The slicer clearance radius of 72.5 mm suggests a head roughly as wide as the pitch.
- **Moving dock carrier** (shuttle, elevator or carousel): the most compatible with the existing kinematics.
  - A second set of 4 docks is moved by an extra motor so that its heads appear at the existing (x, 332.2) poses, or at a slightly different Y with a small travel extension.
  - It needs an extra stepper and driver, homing, sensors, and a mechanism that cannot collide with the gantry.
  - Software would have to treat "dock position k" as shared between two heads.
- **Umbilicals:** every head has a USB+power cable and a PTFE tube. Eight umbilicals to the moving carriage zone make cable management a real constraint (routing details unknown).

---

## 2. Electronics

### 2.1 Host
- The SoC is a Rockchip RK3562 (aarch64, Linux).
- The community reports throttling at about 85 C and mainboard overheating, and has made fan or cooling mods (`refs\SnapmakerU1-Extended-Firmware\docs\panda_breath.md` L37-52). Links:
  - https://makerworld.com/pl/models/2396929
  - https://makerworld.com/pl/models/2464667
  - https://www.reddit.com/r/SnapmakerU1/comments/1tlk27r/
- A Linux host "MCU" is also built (`refs\u1-klipper\lava\klippy_mcu_config`, initial pin gpiochip0/gpio12).
- Peripherals:
  - NFC is on SoC SPI2, and its reset and RF-switch lines are SoC GPIOs (gpiochip1 lines 24, 25, 27, 28; `refs\u1-klipper\klippy\extras\fm175xx_reader.py` L217-225).
  - The Extended Firmware supports the internal MIPI CSI camera plus a USB camera, so at least one user-accessible USB host port exists (`docs\camera_support.md`).

### 2.2 Main MCU (mainboard)
- `[mcu] serial: /dev/ttyS6`, `baud: 921600` (cfg L9-13).
- The firmware config `refs\u1-klipper\lava\at32f403a_config` contains:
  - `CONFIG_MACH_AT32F403A`, 240 MHz, 96 KB RAM, 256 KB flash.
  - Comms: `CONFIG_STM32_USBCANBUS_PA11_PA12_AND_SERIAL_USART5_PB8_PB9`, i.e. serial to the host on USART5 PB8/PB9 plus a USB-to-CAN bridge, with CAN on PB5/PB6 at 500 kbit/s.
  - This option was added by Snapmaker to Klipper's Kconfig: `refs\u1-klipper\src\stm32\Kconfig` L114-121 (AT32 chips), L450-453 (AT USART5), L502-506 (combined USBCAN+serial) and L515-517 (PB5/PB6 CAN for AT32F403A).
  - `INITIAL_PINS` "!PE9,PB2,PC8,PC9,!PA10,!PA15,!PD4,!PD5,!PD6,!PD7,!PE15". These match mainboard functions in printer.cfg (bed heater PE9, cavity fan PC8, power fan PC9, cavity LED PA10, feed motors PD4-PD7, purifier power PE15), which identifies this as the mainboard build.
- Mainboard functions in printer.cfg:
  - X/Y TMC2240 drivers (SPI) and Z TMC2209.
  - Bed heater PE9 with thermistor PC2 (max 100 C).
  - Chamber thermistor PC0; cavity fan PC8 with tach PC7; cavity LED PA10.
  - Purifier: exhaust PA8, inner PA9, tach PA6, power enable PE15, detect PA7.
  - `power_fan`: a heater_fan on PC9 that runs when any of extruder..extruder3 is hot (cfg L314-320). This list would need the new extruders added.
  - Total current sense `I_AD` on PC1 (0.01 Ohm shunt, scale 33.333; cfg L322-327).
  - Power-loss check PB7 (cfg L328-334).
  - 4 dock park ADCs: PB0, PC4, PC5, PB1.
  - 2 feed modules, about 26 pins (section 3).
- Free pins: from config cross-referencing, only PA4, PA5 and PC3 look unreferenced among ADC-capable pins. There is no evidence they reach a connector. The mainboard is effectively full for 4 more dock sensors plus 2 more feed modules.

### 2.3 Toolhead MCUs
- `[mcu e0]` to `[mcu e3]` are USB serial by-path:
  - `platform-xhci-hcd.0.auto-usb-0:1.3:1.0` = e0
  - `1.4` = e1
  - `1.2` = e2
  - `1.1` = e3
  - (cfg L15-28)
  - This is a 4-port USB hub behind one xHCI root port, and every downstream port is used.
- Firmware `refs\u1-klipper\lava\at32f415_config`: `MACH_AT32F415`, 144 MHz, 32 KB RAM, USB serial on PA11/PA12, `INITIAL_PINS` "PB2,!PB5,PB0,!PB3". These are driver enable, heater, hotend fan and part fan, matching the toolhead pin map below.
- Discrepancy: the Extended Firmware simulator overlay names its dummy target `dummy_at32f403a` and says it mirrors the toolhead MCU (`refs\SnapmakerU1-Extended-Firmware\overlays\firmware-extended\41-feature-toolhead-mcu-simulator\README.md`). The build configs in u1-klipper point to AT32F415. See Open questions.
- Per-toolhead pin map (identical for every eN; e.g. `[extruder]` cfg L665-707):

| Function | Pin | Notes |
|---|---|---|
| Extruder step/dir/enable | eN:PA8 / eN:PA9 / !eN:PB2 | rotation_distance 4.95, microsteps 16 |
| Extruder driver | TMC2209 UART eN:PA15, addr 3 | run 0.8 A, hold 0.2 A |
| Hotend heater | eN:PB5 | max_temp 300; `idle_hold_max_power 0.5`, `active_hold_max_power 1` |
| Hotend thermistor | eN:PA2 | NTC 100K |
| Heater power switch | `eN_heat_sw` on !eN:PB7 | output_pin |
| Part fan | eN:PB3, tach eN:PB4 | T0 is `[fan]` with `aux_cool_fan: cavity_fan`; others are `fan_generic eN_fan` |
| Hotend fan | !eN:PB0, tach eN:PA10 | heater_fan with stepped temperature table |
| Active Hall | eN:PB1 | analog_range 0-47000 |
| Grab-valid Hall | eN:PA3 | analog_range 0-390 |
| Filament motion (runout) | eN:PA1 (analog) | detection_length 0.5 (`filament_motion_sensor.py`) |
| Nozzle probe | eN:PA0 `inductance_coil` | frequency 1.2-1.65 MHz |
| Power-loss | eN:PB8 | `[power_loss_check eN]` (cfg L821, L960, L1099, L1237) |
| Accelerometer | e0:PA4 on spi1 (LIS2DW or SC7A20) | T0 only |

- Because a head is a full USB Klipper MCU, Klipper refuses to start if any one is missing. This is why the community built the MCU simulator: `refs\SnapmakerU1-Extended-Firmware\docs\faulty_toolhead.md`. The official guide is https://wiki.snapmaker.com/en/snapmaker_u1/troubleshooting/bypass_a_faulty_toolhead.
- Implication: hot-plug or "optional" heads need firmware support.

### 2.4 Power and thermal budget
- `MAX_HEATING_EXTRUDERS = 2` (`refs\u1-klipper\klippy\extras\heaters.py` L500). A queue (L630-662) lets only 2 hotends ramp at full power at the same time and limits non-active heads to `idle_hold_max_power`.
- The total-current ADC suggests firmware-level power monitoring. No consumer of `I_AD` other than its own module was found in the grep.
- PSU wattage, hotend heater wattage and the 24 V rail current rating are not in the sources (Open questions).
- 4 more heads add four heater loads, about 8 fans and 4 MCUs. The 2-at-a-time heating rule limits peak current, but idle-warm standby of up to 7 parked heads raises the steady-state load.

---

## 3. Filament path: feeders, RFID, runout

### 3.1 Feed modules (`[filament_feed left]` cfg L1245-1283, `[filament_feed right]` cfg L1284-1326; code `refs\u1-klipper\klippy\extras\filament_feed.py`, 2008 lines)
- There are 2 modules with 2 channels each (`FEED_CHANNEL_NUMS = 2`).
- Each module has one DC motor:
  - Direction A drives channel 1 and direction B drives channel 2 through a clutch.
  - `_put_into_drive` and `_hang_neutral` engage and disengage it (filament_feed.py L715-743, L785-787).
  - Reduction is 33:1; wheel circumference 31.4159 mm.
- Defaults: `FEED_PRELOAD_LENGTH` 950 mm and `FEED_LOAD_LENGTH_MAX` 1100. The Extended Firmware raises the preload limit to 2500 (`docs\filament_feeders.md`). `load_position` is 150,5.
- Pins:
  - Left module:
    - Lights PE4/PE0 and PD10/PE1.
    - Port-detect ADC PA3 and PA2 (module-present threshold 0.9).
    - Wheel tachs PE5/PE6 and PD1/PD0.
    - Motor PD7/PD6, motor tach PD15.
  - Right module:
    - Lights PE3/PE2 and PD11/PE10.
    - Port ADC PA1 and PA0.
    - Wheel tachs PD12/PD13 and PD9/PD8.
    - Motor PD5/PD4, motor tach PD14.
  - In total about 13 main-MCU pins per module.
- Mapping (`_FILAMENT_FEED_VARIABLE`): module_sequence `'left','left','right','right'`, channel_sequence `1,0,0,1`. So T0/T1 feed from the left module and T2/T3 from the right. `filament_entangle_detect` per head references the same left/right split.

### 3.2 RFID / NFC (`[fm175xx_reader]` cfg L44-61; `refs\u1-klipper\klippy\extras\fm175xx_reader.py`)
- There are 2 FM17580 readers: SoC SPI bus 2 dev 0 ("soc") and dev 1 ("extra"), at 500 kHz.
- Each reader has 2 antennas selected by RF-switch GPIOs (`rf_1` gpiochip1 line 27, `rf_2` line 24). Resets are on lines 25 and 28.
- Channel map: soc_ch_1 is 3, soc_ch_2 is 2, extra_ch_1 is 0, extra_ch_2 is 1.
- `FM175XX_CHANNEL_NUMS = 4` (L7). Selection logic is at L274-301.
- Tags are Mifare Classic 1K (Extended Firmware `docs\design\rfid.md`).
- 4 more channels would need either a third and fourth reader (another SPI chip select and RF GPIOs on the SoC, likely unavailable) or external readers:
  - Network ESP32-C3 + PN532 readers: https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader and https://gitlab.com/baze/snapmaker-u1-drybox-nfc-reader
  - OpenRFID: https://github.com/suchmememanyskill/OpenRFID

### 3.3 Runout and filament detection
- Each head has a `filament_motion_sensor` on eN:PA1 (encoder or analog, detection_length 0.5).
- The feed modules have port-detect ADCs plus wheel tachometers.
- `filament_detect.py` L15: `FILAMENT_DT_CHANNEL_NUMS = 4`.

---

## 4. Constraints and opportunities for 4 more toolheads

### 4.1 Mechanical
| Constraint | Detail | Options |
|---|---|---|
| No free XY for docks | Docks at Y 332.2, Y max 335; X 0-271 fully used at 67.5 mm pitch | Extend Y; front docks at Y < 0; motorized dock carrier presenting heads at existing poses |
| Rear service zone already used | Purge, cut and wipe at about Y 300 per dock; Y idle 250 | Keep the second-row approach path clear of this hardware, or move purge |
| Gantry mass and resonance | Input shaper tuned at X 54 / Y 47.5 Hz (cfg L77-97); longer Y changes it | Re-tune; only T0 has an accelerometer |
| Head size | Clearance radius 72.5 mm, height to rod 27.5 mm (Orca profile) | Second-row docks need the same pitch |
| Grab slide | ±10 mm X slide, grab direction depends on dock position (T0 reversed) | Any new dock needs 10 mm of free X on its grab side |
| Umbilicals | 8 cables and PTFE tubes to the carriage area | Cable chain or carrier redesign; rear-panel pass-throughs |
| Enclosure | Enclosed machine with purifier and cavity fan | Rear extension box, or external dock housing for a carrier |

### 4.2 Electrical
| Constraint | Detail | Options |
|---|---|---|
| USB hub full | e0-e3 on hub ports 1.1-1.4 | Add a powered USB hub (e.g. off the user USB port); by-path names change; check host USB bandwidth and power |
| Dock sensors | 4 ADCs on the main MCU used; about 3 unreferenced ADC pins, connector status unknown | Extra MCU (USB or CAN) with digital or ADC park inputs; `park_detector` supports both |
| Feed modules | Each uses about 13 main-MCU pins; no spare | 2 extra modules driven by an extra MCU, or external feeders and buffers (e.g. PopStation mini) |
| NFC | 2 readers / 4 antennas on SoC SPI2; constants = 4 | External network RFID readers; firmware changes |
| Power | PSU rating unknown; 2-heaters-at-once rule; idle hold 0.5 | Measure PSU headroom with `I_AD`; keep parked heads cold or lower idle power; maybe add a separate 24 V supply for the extra heads |
| Thermal | RK3562 throttles at about 85 C; mainboard cooling is a known issue | Board cooling mod; check host CPU load with 9 MCUs |
| CAN | Main MCU firmware has a USB-CAN bridge with CAN on PB5/PB6 | If broken out, it could host CAN toolhead or expansion boards. Unverified |
| power_fan list | `heater:` lists only extruder..extruder3 | Extend config |

### 4.3 Firmware constants touching hardware (detail belongs in the software report)
- `max_physical_extruder_num: 4` (cfg L115)
- `PHYSICAL_EXTRUDER_NUM = 4` (`klippy\extras\print_task_config.py` L9, `klippy\extras\print_stats.py` L10)
- `FM175XX_CHANNEL_NUMS = 4`, `FILAMENT_DT_CHANNEL_NUMS = 4`
- Per-T0..T3 macros in `xyz_offset_calibration.cfg` and `fluidd.cfg`
- Logical T4-T31 macros already exist and map to physical heads through `SWITCH_OF_EXTENDED_EXTRUDER` (`klippy\toolhead.py` L694-713; `lava\fluidd.cfg` L67-177). This is a useful hook for 8 logical-to-physical slots.
- Positive: the extruder loader iterates up to 99 sections and the park/pick code is fully data-driven (`xy_park_position`, `extruder_grab_dir`). So adding `[extruder4]`..`[extruder7]` with their own MCUs and park detectors is structurally supported.

### 4.4 Opportunities
- The pure-XY docking makes any reachable pose a valid dock. A carrier only has to present heads repeatably to within about 1 mm.
- Per-head MCUs mean new heads are "plug in another USB device". No mainboard driver channels are consumed per head, only one park sensor.
- `park_detector` accepts digital inputs, so dock sensors on a cheap extra MCU (or even a microswitch) work.
- The heating queue already supports staggering many heads within a power budget.

---

## 5. Community mods and prior art

| Item | What | Source |
|---|---|---|
| Toolhead MCU simulator | Runs the printer with a dead or missing head by faking its MCU | `refs\SnapmakerU1-Extended-Firmware\overlays\firmware-extended\41-feature-toolhead-mcu-simulator\README.md`; `docs\faulty_toolhead.md`; https://wiki.snapmaker.com/en/snapmaker_u1/troubleshooting/bypass_a_faulty_toolhead |
| Logical tools T4-T31 | Stock firmware maps up to 32 logical tools to 4 physical heads | `refs\u1-klipper\lava\fluidd.cfg` L67-177; `klippy\toolhead.py` L694-713 |
| External RFID readers | ESP32-C3 + PN532 network readers; OpenRFID | https://github.com/wasikuss/snapmaker-u1-remote-rfid-reader, https://gitlab.com/baze/snapmaker-u1-drybox-nfc-reader, https://github.com/suchmememanyskill/OpenRFID |
| Feeder relocation | BIQU PopStation mini under the printer, 2000 mm preload; Extended Firmware raises the limit to 2500 mm | `docs\filament_feeders.md`; https://neo.bttwiki.com/en/docs/more-series/pop-module/popstation-mini/ |
| Speed tiers / dock speed | Higher max-speed tiers; dock grab speed up to 50 mm/s | `docs\tweaks.md` L57-100; https://github.com/JNP-1/Snapmaker-U1-Config |
| Mainboard / SoC cooling | Fan mods for the RK3562 overheating | `docs\panda_breath.md` L37-52 and the links in 2.1 |
| AFC-lite UI | AFC (Armored Turtle) style UI stub for lanes | `docs\afc-lite.md` |
| Physical second row / 8 heads | No prior art found in local sources (web search was not possible) | - |

---

## Open questions
1. **PSU.** What is the PSU wattage and the 24 V rail rating? What is the per-hotend heater wattage? Can it hold 8 heads at idle temperature plus the bed?
2. **Frame depth.** How much physical depth is there behind the dock row, inside or outside the enclosure? What are the exact frame and rear-panel dimensions, and can the Y rails and belts be lengthened?
3. **Front clearance.** Is there room in front of Y = 0 for front docks, given the door and the bed at high Z?
4. **Dock hardware.** What is the dock and latch geometry (drawings or CAD)? Where is the dock park sensor (Hall or switch)? How is the analog divider wired? Are the docks a single rail part or separate modules?
5. **USB.** Which hub chip is used? Is there a free hub port or root port on the RK3562 board? Can the user USB port supply a hub with 4 more MCUs?
6. **Toolhead MCU.** Is it really AT32F415, as the u1-klipper config says, or AT32F403A, as the simulator naming suggests?
7. **Spare mainboard pins.** Are PA4, PA5 and PC3 free and broken out? Are there unpopulated headers?
8. **CAN.** Is the main MCU's CAN (PB5/PB6) wired to a transceiver and connector?
9. **Umbilicals.** How are the head cables and PTFE routed (cable chain, slack loop), what are their lengths, and where are the connectors?
10. **Purge/wipe hardware.** What is the exact location and footprint of the per-dock purge, cut and wipe hardware near Y 300?
11. **Host headroom.** What is the host CPU and USB load with 8 toolhead MCUs, given the RK3562 thermal issues?
12. **Prior art beyond local sources.** Are there wiki pages, teardowns or community projects that the declined WebFetch calls would have found?
