# 03 – Host software and UI layers (Moonraker, Fluidd, touchscreen GUI, Snapmaker Control)

Scope: how the host-side software of the Snapmaker U1 (Moonraker fork, Fluidd fork, stock touchscreen GUI, Snapmaker Control / Orca device page, cloud/app) would cope with a second row of toolheads (about 8 tools instead of 4).

Sources (read-only clones under `C:\Users\N\u1-second-row\refs\`): `u1-moonraker`, `u1-fluidd`, `snapmaker_control`, plus cross-references into `u1-klipper`, `OrcaSlicer` and `SnapmakerU1-Extended-Firmware`. Method: grep and read of local files only. No upstream diffing or network access was used (fork changes were found through Snapmaker copyright headers and markers). Line numbers refer to those clones.

---

## Key findings

1. **The open-source host layers are almost count-agnostic.**
   - **Moonraker:** only two spots are fixed at 4, both in `machine.py`: the extruder→index subscription dict and the 4-element nozzle-diameter defaults. Everything else is list-based: metadata, print-start parameters, cloud print and file handling.
   - **Fluidd:** the fork is stock upstream 1.36.2 with no Snapmaker changes found. It discovers `extruder\d{0,2}` and `T\d+` dynamically, so it would show 8 extruders and 8 tool buttons without changes.
2. **The real 4-tool limits in the print path are in Klipper and in closed clients.**
   - **Klipper:** `print_task_config.py` sets `PHYSICAL_EXTRUDER_NUM = 4`. It rejects any `MAP_TABLE` entry ≥ 4 and validates saved array lengths against 4. This is Klipper's domain but gates every UI.
   - **Flutter device page:** used by Snapmaker Orca and Snapmaker Control. It hardcodes `extruder`…`extruder3`, two `filament_feed` units (left/right), 4 extruder icons and "N/4" strings.
3. **The stock touchscreen GUI (`/usr/bin/gui`) is a closed binary, but it can be replaced.**
   - It is supervised by `lmd`, which forks it from a compiled-in path.
   - The Extended Firmware already swaps in the open-source **HelixScreen** by bind-mounting it over `/usr/bin/gui`.
   - The stock GUI's behaviour with 8 extruders is unknown. It is closed and untested, and is most likely to show only 4 tools or misbehave.
4. **Closed and proprietary parts:**
   - `/usr/bin/gui`, `lmd`, `unisrv` (C++ LanManager / mqtt_agent), the Snapmaker cloud/app, and Snapmaker Control (a Dart AOT binary whose licence forbids reverse engineering).
   - None of these can be changed without Snapmaker.
5. **Feasibility.** 8-tool support is realistic on an open stack:
   - Klipper + Moonraker (patch 2 lines) + Fluidd/Mainsail (stock) + HelixScreen or no touchscreen + Orca printing via plain Moonraker upload.
   - The tool-remap step before a print is the main missing piece outside the closed clients. It can be done with macros, AFC-style lanes, or a small Fluidd dialog.
   - The stock "Snapmaker experience" cannot be made 8-tool by the community: touchscreen, app, cloud, and Orca's device page with its filament mapping dialog.

---

## 1. Snapmaker-specific changes

### 1.1 Moonraker fork (`refs\u1-moonraker`)

The fork is based on upstream v0.9.3 as a single squashed commit, "Release firmware version 2.0.0". The table lists the Snapmaker additions and changes.

| Component / file | What it adds | Relevance to tool count |
|---|---|---|
| `components\snapmakercloud.py` (1772 lines, new) | Endpoints registered over **MQTT/WS only, not HTTP** (lines 125–155): `/server/files/get_status`, `pull`, `start_local_print`, `start_cloud_print`, `cancel_pull`, `list_page`, `thumbnails_base64`, `get_userdata_space`. Notifications `smcloud:file_pull_progress` and `smcloud:devie_info_update` (156–157). `/server/gcode/enable_output` and `disable_output` (162–172). `_handle_start_local_print(path, options, print_plate, extra_info)` (205–235). `start_cloud_print(url, auto_start, checksum, type, size, print_plate, options, extra_info)` (237–266). Job events via `notify_device_state_changed` (around 599). `_handle_3mf`: extracts `plate_N.gcode` for N in `range(1,36)` and requires `'Snapmaker U1' in printer_model` from `project_settings.config` (1124–1239, check at 1211). `process_local_file` → `kapi.start_print_advanced(..., options=options)` (1543–1694, call at 1633). `check_can_print` uses `print_stats` and `machine_state_manager.main_state == 0` (1696–1734). | Passes the `options` dict (including `map_table`) through opaquely. Not count-limited. The model-name check matters if profiles are renamed. |
| `components\klippy_apis.py` (changed) | `/printer/control/extruder_temp` (index→`T`, map→`A`) plus control endpoints for led, main_fan, generic_fan, bed_temp, print_speed and emergency stop (101–106, 244–257). `_fill_metadata` (288–317) appends slicer metadata as gcode params: LINE_WIDTH, LAYER_HEIGHT, NOZZLE_DIAMETER_LIST, NOZZLE_TEMP, FILAMENT_TYPE, FILAMENT_FLOW_RATIO, FILAMENT_DIAMETER, FILAMENT_MAX_VOLUMETRIC_SPEED, FILAMENT_USED_G/MM, FILAMENT_VOLUME_TYPE, PRINT_SEQUENCE, speed/accel lists, PROCESS_FLOW_SUPPORT, SLICER, SLICER_VERSION. `start_print_advanced` (347–379) builds `SDCARD_PRINT_FILE_WITH_PARAMETERS FILENAME="…" KEY="value" …`. Plain `start_print` still uses `SDCARD_PRINT_FILE` (381–404). | Index-based. Klipper does the validation. No 4 in Moonraker. |
| `components\machine.py` (changed) | `MACHINE_TYPE="Snapmaker U1"` and `product_info.json` (80–81). Subscribes to `machine_state_manager` and to each extruder's `nozzle_diameter`, then persists them to product_info (202–261). `product_info_default` (1035). `/machine/set_device_name` and `/machine/heartbeat` (1111–1140). | **Hardcoded 4**, see table below. |
| `components\file_manager\metadata.py` (changed) | Slicer detection `SnapmakerOrca` (418). Extra `SUPPORTED_DATA` fields (1186–1221): filament_colour, filament_multi_colors, filament_colour_mode, filament_used_mm, nozzle_temp, nozzle_diameter_list, filament_volume_type, process_flow_support, print_sequence, outer-wall lists and more. | All per-tool lists, so they scale. Upstream `referenced_tools` and `extruder_colors` are missing; the Extended Firmware AFC mod backports them (`overlays\mods\afc\02-patch-moonraker\patches\home\lava\moonraker\01-metadata-b8b28bc-5b92e52.patch`). |
| `components\file_manager\file_manager.py` (changed) | USB mount monitoring (120–233, 1331–1380), `/server/files/usb_rescan` (158), storage_type filter (1144–1184), user space (887, 921). | None. |
| `components\repeater.py` (new) | `/camera/*` and `/system/*` (get_device_info, upgrade, …) proxied over MQTT to `unisrv` via `camera/request|response` and `system/request|response` (57–159). | Device info comes from closed `unisrv`. |
| `components\client_manager.py` (new) | `/server/client_manager/*`: info, approve, disconnect_all, set_link_mode, set_region, logout, refresh_access_code, refresh_pin_code (47–179). Subscribes to `lan_manager/screen_event` ("C++ LanManager") and `mqtt_agent/notification`. Comment: "GUI endpoints (HTTP/WebSocket → forward to unisrv)". | LAN/cloud pairing. No tool count. |
| `components\exception_manager.py` (new) | Module IDs MOTION=522, TOOLHEAD=523, CAMERA=524, SYSTEM=2052 (43–53). Notifications `snapmaker:exception_notification` and `snapmaker:exception_status`. | Toolhead exceptions carry an `index`. Whether the encoding limits it to 0–3 is unknown. |
| `components\mqtt.py` (changed) | Instance name from `.lava.sn` (344–354). Topics `<sn>/request|response` and `moonraker/status`, which `unisrv` bridges to `<sn>/status` (402–413). `status_objects` from config (414–428). | Which objects are pushed to the app is configured in `moonraker.conf`, which was not available locally. It may list `extruder`…`extruder3` explicitly. |
| `components\zeroconf.py` (changed) | `_snapmaker._tcp.local.` with version, machine_type, device_name, sn, link_mode, userid, ip and region. Hostname `U1-<sn>.local` (38, 153–185). | Discovery only. |
| `components\httpx_client.py` (new) | HTTP client for cloud downloads. | None. |
| `spoolman.py`, `simplyprint.py` | Upstream and generic. | Not limited to 4. |

### 1.2 Fluidd fork (`refs\u1-fluidd`)

- The fork is stock upstream 1.36.2. A grep for `snapmaker`, `lava`, `U1`, `extruder3`, `filament_detect` and `print_task` found no Snapmaker-specific code.
- Extruders are discovered dynamically: `src\store\printer\getters.ts:403–405` uses `/^extruder\d{0,2}$/` (up to `extruder99`).
- Tool macros are discovered dynamically: `src\components\widgets\toolhead\ToolChangeCommands.vue:79–108` uses `/^t\d+$/i`, laid out 6 per row. Eight tools would wrap to two rows.
- There is no filament-slot, RFID or `map_table` UI. Prints start with plain `SDCARD_PRINT_FILE`, so the slicer's T-numbers map 1:1 onto physical extruders through Klipper's default map.
- The Extended Firmware does not use this fork. It installs upstream Fluidd **v1.37.6** (`SnapmakerU1-Extended-Firmware\overlays\firmware-extended\62-app-fluidd\pre-scripts\01-install-fluidd.sh:13`).
- The Extended Firmware's AFC-lite stub (`docs\afc-lite.md`) gives Fluidd/Mainsail a lane UI, but it "maps U1's 4 extruders to AFC lanes (E0-E3)".

### 1.3 Snapmaker Control (`refs\snapmaker_control`)

- The clone contains only `README.md`, `LICENSE.txt` and `THIRD_PARTY_NOTICES.txt`.
- The product is a proprietary Dart AOT binary (Dart SDK 3.11.5; packages mqtt5, multicast_dns, dio, hive_ce, get_it, pointycastle). It serves a closed **Flutter Web** UI (`web/flutter_web`). THIRD_PARTY_NOTICES lines 1839–1849 call out the proprietary packages and Flutter Web assets.
- The README says "See up to 4 filament slots".
- `LICENSE.txt:104` forbids reverse engineering.
- The same Flutter bundle ships inside Snapmaker Orca at `OrcaSlicer\resources\web\flutter_web\main.b347974c91352c2f.js`. That is the device/print-send page. Observed hardcoding:
  - Line 139979: `["print_task_config","extruder","extruder1","extruder2","extruder3"]`.
  - Line 187791: subscription list with `extruder`…`extruder3`, `"filament_feed left"`, `"filament_feed right"`, `machine_state_manager`, `filament_detect`, `defect_detection`, `purifier`, …
  - Line 35203: the `print_task_config` field model.
  - Lines 39801–39819: `map_table` becomes `SET_PRINT_USED_EXTRUDERS EXTRUDERS=…` plus `SET_PRINT_PREFERENCES …`.
  - Line 152570: `map_table` is put into the start options.
  - Assets `svgs\extruder\iconExtruder1–4.svg`.
  - `i10n\en.json:415–428`: "Cleaning Nozzle N (N/4)", "Calibrating Toolhead 1..4", "Toolhead 1..4 Calibrating extrusion flow".
- Orca native code is not hardcoded to 4:
  - `src\slic3r\Utils\MoonRaker.cpp:2507–2540` sends `server.files.start_local_print` or `start_cloud_print` over MQTT.
  - `src\slic3r\GUI\SSWCP.cpp:1657–1749` parses the machine filament sync (nozzle_diameters, filament_vendor/type/sub_type/color_rgba, extruder_map_table, filament_official, filament_color_multi) by array size.
  - `SSWCP.cpp:2759–2811` passes the web page's parameters through.

---

## 2. Where "4" is hardcoded

| Location | Hardcoding | Change needed for 8 |
|---|---|---|
| `u1-moonraker\moonraker\components\machine.py:202–205` | `_extruder_subscription = {"extruder":0,"extruder1":1,"extruder2":2,"extruder3":3}` | Add `extruder4`…`extruder7`, or better, build it from `printer.objects.list` matching `^extruder\d*$`. Trivial. |
| `u1-moonraker\moonraker\components\machine.py:206` | `_last_nozzle_diameter = [0.4]*4` (literal 4-element list) | Size it from the discovered extruder count. Without this, indices 4–7 raise IndexError or are dropped. |
| `u1-moonraker\moonraker\components\machine.py:1035` | `product_info_default "nozzle_diameter": [0.4,0.4,0.4,0.4]` | Use 8 entries. Also migrate existing `product_info.json` files that hold 4. |
| `u1-moonraker\...\snapmakercloud.py:1211` | 3mf is rejected unless `'Snapmaker U1' in printer_model` | Not a count, but an 8-tool printer profile must keep "Snapmaker U1" in its model name, or the check must be relaxed. |
| `u1-moonraker` `moonraker.conf` `[mqtt] status_objects` (not in the repo) | Probably lists `extruder`…`extruder3` | Add `extruder4–7` so the app/cloud receive them (moot unless the closed clients are updated). |
| `u1-klipper\klippy\extras\print_task_config.py:9` (Klipper) | `PHYSICAL_EXTRUDER_NUM = 4`. Default arrays (26–61, 92–98) and length validation (199–214) depend on it. Extruder lookup loops over `extruder`/`extruder{i}` for i<4 (around 1148–1156). `map_table[1] < PHYSICAL` check (1175). | Set to 8. Migrate saved configs, since the length check would otherwise reject old 4-length state. `LOGICAL_EXTRUDER_NUM = 32` is already enough. Covered in the Klipper report. |
| Flutter bundle (Orca `resources\web\flutter_web\main.*.js:139979, 187791`; Snapmaker Control) | Subscribes to `extruder`…`extruder3` only; two `filament_feed` objects (left/right) | Needs Snapmaker. Closed and compiled; the licence forbids patching. |
| Flutter assets `svgs\extruder\iconExtruder1–4.svg`, `i10n\en.json:415–428` | 4 icons; "N/4" and "Toolhead 1..4" strings | Needs Snapmaker. |
| `snapmaker_control\README.md` | "See up to 4 filament slots" | Needs Snapmaker. |
| `/usr/bin/gui` (stock touchscreen, closed) | Unknown. Almost certainly 4 tool tiles, 4 filament slots, and 4-toolhead calibration wizards. | Cannot be changed. Replace it (HelixScreen) or run headless. |
| `unisrv` / cloud / mobile app (closed) | Unknown. Possibly validates or reports 4 slots. | Needs Snapmaker. |
| `filament_detect` (Klipper object, `Extended-Firmware\docs\design\filament_detect.md:88`) | Channel `0..3`; UIs read `info[channel]` | Extend to 8 channels (Klipper/RFID side). The UI side is index-based. |
| `Extended-Firmware\overlays\firmware-extended\64-app-openrfid\...\openrfid_u1_base.cfg` | 2 readers (left/right) × upper/lower coil = 4 slots | Add readers or coils for row 2. Hardware plus config. |
| `Extended-Firmware\docs\faulty_toolhead.md` (firmware-config UI) | 4 fixed rows mapping Toolhead 1–4 to `[extruder]…[extruder3]`, `[mcu e0..e3]` and `e0..e3_nozzle_fan` | Add 4 rows (open source). |
| `Extended-Firmware\docs\afc-lite.md` (AFC stub) | Lanes E0–E3 | Extend to E0–E7 (open source). |
| `u1-fluidd\src\store\printer\getters.ts:405`, `ToolChangeCommands.vue:83` | **None.** Dynamic regexes. | No change. An optional remap dialog is a nice-to-have. |
| `u1-moonraker\...\file_manager\metadata.py` | **None.** Per-tool lists. | No change. Optionally backport `referenced_tools` (AFC patch exists). |
| `u1-moonraker\...\klippy_apis.py` `_fill_metadata` / `start_print_advanced` | **None.** Passes lists and strings through. | No change. |
| OrcaSlicer `SSWCP.cpp` / `MoonRaker.cpp` | **None** in native code (iterates by array size) | No change on the native side. The slicer profile is a separate topic. |

---

## 3. Metadata and print-start flow (slicer → Moonraker → UI → Klipper)

### Stock path (Snapmaker Orca / app)

1. **Slice.** Snapmaker Orca writes the G-code or 3mf. The header metadata contains per-tool lists such as `filament_colour`, `filament_type`, `nozzle_diameter`, `nozzle_temperature`, flow ratio and `filament_used_mm/g`. The 3mf carries `project_settings.config` with `printer_model`.
2. **Device state to the UI.** The Flutter device page subscribes over MQTT (`<sn>/request|response`, status via `moonraker/status` → `unisrv` → `<sn>/status`) to:
   - `print_task_config`, which holds the current `extruder_map_table`, preferences and the filament info cached per physical extruder;
   - `filament_detect`, the RFID results per channel 0–3;
   - `extruder`…`extruder3` and `filament_feed left/right`.
   Orca's `SSWCP.cpp:1657–1749` turns the machine filament sync into the slicer's filament list.
3. **Remap dialog.** The Flutter page compares the slicer's filaments (logical T0…Tn, up to 32) with what is loaded in physical extruders 0–3. The user confirms a `map_table` of [logical, physical] pairs.
4. **Start.** Orca/the app sends `server.files.start_local_print` (local file) or `server.files.start_cloud_print` (URL plus checksum) over MQTT (`MoonRaker.cpp:2507–2540`). The `options` dict includes `map_table`, bed leveling, flow calibrate, shaper calibrate, timelapse and end-unload, plus `print_plate` and `extra_info` (cloud user and task ids).
5. **Moonraker.**
   - `snapmakercloud.process_local_file` downloads the file if needed. For a 3mf it checks the U1 model and extracts `plate_N.gcode`.
   - It checks `check_can_print` (print_stats idle and `machine_state_manager.main_state == 0`).
   - It calls `klippy_apis.start_print_advanced`, which emits:
     `SDCARD_PRINT_FILE_WITH_PARAMETERS FILENAME="…" MAP_TABLE="…" BED_LEVEL=… … NOZZLE_DIAMETER_LIST="…" FILAMENT_TYPE="…" …`
     The options are upper-cased, and `_fill_metadata` adds the parsed metadata.
6. **Klipper.**
   - `virtual_sdcard.py:357–369` calls `print_task_config.cmd_SET_PRINT_TASK_PARAMETERS`. It validates `MAP_TABLE` (physical index < `PHYSICAL_EXTRUDER_NUM` = 4) and stores the per-extruder preferences.
   - During the print, `virtual_sdcard` remaps T-commands through `extruder_map_table` (around lines 2175–2181).
   - The Flutter page can also set the map ahead of time with `SET_PRINT_USED_EXTRUDERS EXTRUDERS=…` and `SET_PRINT_PREFERENCES …` (bundle lines 39801–39819). Klipper also has `SET_PRINT_EXTRUDER_MAP` / `GET_PRINT_EXTRUDER_MAP` (`print_task_config.py:535–570`).
7. **Feedback.** Job state goes back through `notify_device_state_changed` (MQTT → unisrv → cloud/app). Errors go through `exception_manager` (module 523 = TOOLHEAD, with an index).

### Open path (Fluidd / Mainsail / plain Orca upload)

- The upload goes through the standard `/server/files/upload`.
- The print starts with `SDCARD_PRINT_FILE`, with no options and no metadata parameters.
- Klipper uses the persisted or default `extruder_map_table`, which is identity by default.
- Remapping must be done beforehand with `SET_PRINT_EXTRUDER_MAP`, through macros, or with the AFC-lite lanes.
- Nothing in this path is limited to 4 except Klipper's `PHYSICAL_EXTRUDER_NUM`.

### Implication for 8 tools

The Moonraker part of the flow scales unchanged. The limits are Klipper's physical-index check and the closed Flutter remap dialog, which only knows 4 physical slots.

---

## 4. Touchscreen UI

- **What it is.** `/usr/bin/gui` is a closed-source ELF.
  - The closed supervisor `/usr/bin/lmd` forks it from a compiled-in path and validates it via `/proc/<pid>/exe`.
  - It draws to `/dev/fb0`. The framework (Qt, LVGL, Flutter-embedded, …) was not determined.
  - It talks to Moonraker over websocket/HTTP. `client_manager.py` documents "GUI endpoints (HTTP/WebSocket → forward to unisrv)", and `lan_manager/screen_event` comes from unisrv.
  - Its state lives in `/oem/printer_data/gui/`.
  - `limits-helper.sh` in the Extended Firmware lists processes nginx, unisrv, gui and wpa_supplicant.
- **Can it be modified?** Not in any practical sense. There is no source, and it is proprietary. It **can be replaced**:
  - The Extended Firmware hook `overlays\firmware-extended\69-app-helixscreen\root\etc\hooks\lmd.d\30-helixscreen.sh` bind-mounts the open-source **HelixScreen** ELF read-only over `/usr/bin/gui`.
  - lmd still supervises it (`HELIX_SUPERVISED=1`). It renders through DRM (`/dev/dri/card0`) and mirrors frames to `/dev/fb0` for the remote-screen `fb-http`.
  - Unmounting restores the stock GUI. See `docs\helixscreen.md:56–66`.
  - Caveat (`docs\helixscreen.md:85`): `lmd` does not start at all if the camera is disabled, and then no GUI runs.
- **Does it block 8 tools?** For the stock GUI, effectively yes.
  - Its tool tiles, filament-slot screens, RFID flows, calibration and nozzle-clean wizards almost certainly assume 4 tools. The companion Flutter UI has "N/4" strings and 4 icons.
  - It may ignore `extruder4–7` (best case) or crash or show wrong data (worst case). This is untested.
  - It does not block the machine itself. Klipper and Moonraker run independently, and the GUI can be swapped for HelixScreen or simply left in place while using Fluidd.
  - HelixScreen is open source, so 8-tool support there is a normal code contribution if it does not already handle N tools.

---

## 5. Feasibility and effort

| Layer | Open/closed | Effort for 8 tools | Notes |
|---|---|---|---|
| Moonraker fork | Open (GPLv3) | **Small**: about 3 lines in `machine.py` plus a product_info migration. Optionally add `extruder4–7` to `status_objects`. | Everything else is list-based. Keep "Snapmaker U1" in `printer_model` or relax `snapmakercloud.py:1211`. |
| Fluidd (fork or upstream) | Open (GPLv3) | **None** for basic use. **Small to medium** for an optional pre-print remap dialog (read `print_task_config`, send `SET_PRINT_EXTRUDER_MAP` or start via the advanced command). | Mainsail is similar. AFC-lite stub: extend lanes to E0–E7. |
| Extended Firmware UI bits (firmware-config, AFC-lite, OpenRFID cfg, remote screen) | Open | **Small to medium** | Rows, lanes and RFID channels for 4 more tools. RFID needs hardware. |
| HelixScreen (touchscreen replacement) | Open | **Unknown to medium**, depending on its current max tool count and U1 support | The only realistic on-printer touchscreen for 8 tools. |
| Klipper `print_task_config` | Open (GPLv3) | Small code change, medium testing | Owned by the Klipper report. Gates all start paths. |
| Stock touchscreen `/usr/bin/gui` + `lmd` | **Closed** | Not feasible | Replace or tolerate. |
| Flutter device page (Snapmaker Orca, Snapmaker Control) | **Closed**, licence forbids RE | Not feasible | Use plain Moonraker/Klipper upload in Orca (generic Klipper host) instead of the Snapmaker device page. |
| `unisrv`, cloud, mobile app | **Closed** | Not feasible | The cloud/LAN app workflow stays at 4 tools. |

**Overall.** The host-software side is not the hard part. An 8-tool U1 on a fully open stack needs:
- about a day of Moonraker and Fluidd work;
- the Klipper `PHYSICAL_EXTRUDER_NUM` change;
- a HelixScreen or no-touchscreen decision.

What you lose is the Snapmaker-branded UX: the touchscreen wizards, the app/cloud, and the Orca device page's automatic RFID filament mapping. Replicating the remap dialog in an open UI (Fluidd panel or HelixScreen) is the main new piece of work.

---

## Open questions

1. What framework is the stock `/usr/bin/gui` built on (Qt, LVGL, Flutter embedded)? Does it enumerate extruders dynamically or hardcode 4?
2. How does the stock GUI behave when `extruder4`…`extruder7` exist? Does it ignore them, crash, or mis-index? This needs a test on hardware or with a mocked Klipper.
3. What does the on-device `moonraker.conf` `[mqtt] status_objects` contain? It is not in the clone.
4. Do `unisrv`, the cloud or the app validate the extruder count or `map_table` length?
5. Do the Snapmaker Control release notes or roadmap mention more than 4 slots? GitHub releases could not be fetched (no network).
6. What is HelixScreen's maximum tool count, and how far does its U1 support go (filament_detect, print_task_config remap)?
7. Does the stock GUI or Flutter page depend on `filament_detect.info` having exactly 4 entries?
8. How is the exception `index` encoded for TOOLHEAD (523) errors? Is it limited to 0–3? Nothing turned up in `deviceError.json`.
9. Will an 8-tool printer profile keep `printer_model` containing "Snapmaker U1" (the 3mf gate at `snapmakercloud.py:1211`)?
10. How do the two `filament_feed` objects (left/right) generalise to a second row? Would this be 4 feeders, or 2 with more channels? This depends on the hardware design.

Note: an early, partially successful command left upstream clones in `/tmp/upstream` (moonraker, fluidd v1.36.2). They were not used for this report and can be deleted.
