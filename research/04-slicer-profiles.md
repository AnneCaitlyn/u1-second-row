# 04 — Slicer & Printer Profiles for an 8-Toolhead Snapmaker U1

Scope: Snapmaker fork of OrcaSlicer (`refs/OrcaSlicer`, HEAD `4996d50` "Update the process to 02.03.04.03 (#1005)", origin `github.com/Snapmaker/OrcaSlicer`) and `refs/snapmaker-profiles` (HEAD `787b898`, origin `github.com/Snapmaker/snapmaker-profiles`). Both carry profile bundle version `02.03.04.03`. The U1 machine profiles are identical in both repos. The only differences are a few filament files, plus the cover/bed images that exist only in OrcaSlicer.

All paths below are relative to `C:\Users\N\u1-second-row\refs\`. Line numbers are from the checked-out HEADs.

---

## Key findings

1. **The slicer itself is not limited to 4 tools.** `MAXIMUM_EXTRUDER_NUMBER = 64` and `MAXIMUM_FILAMENT_NUMBER = 64` (`OrcaSlicer/src/libslic3r/libslic3r.h:65,68`). The extruder count is not a scalar. It comes from the length of the `nozzle_diameter` array (`Preset::normalize`, `OrcaSlicer/src/libslic3r/Preset.cpp:384-402`). Giving every per-extruder array 8 elements produces an 8-extruder printer.
2. **The tool change gcode does not depend on the tool count.** The U1 `change_filament_gcode` (quoted in §1.4) only uses `next_extruder`, `previous_extruder`, `temperature[next_extruder]` and so on. It emits `M104 S.. T<n>`, `M400`, `T<n>` and `SM_PRINT_PREEXTRUDE_FILAMENT INDEX=<n>`. It works unchanged for T4–T7, provided the firmware accepts them.
3. **The 4-tool assumption is hardcoded in exactly one place in the profiles: `machine_start_gcode`.** It contains an unrolled per-tool sequence for EXTRUDER 0..3 (`SM_PRINT_EXTRUDER_PREHEAT`, `SM_PRINT_AUTO_FEED` and `SM_PRINT_FLOW_CALIBRATE`, then `M104 S0 T0..T3 A0`). For 8 tools this block must be extended, ideally wrapped in `is_extruder_used[n]` guards.
4. **An 8-tool U1 can be done as a user-profile JSON with no fork code changes for slicing.** The user printer preset should inherit `Snapmaker U1 (0.4 nozzle)`. It must keep `printer_model = "Snapmaker U1"` and a name containing "Snapmaker U1", because several code paths are gated on that string:
   - the WipeTower2 `M220 B/R` speed-factor handling (`WipeTower2.cpp:998-1013,1325`)
   - the tower-interface options (`ConfigManipulation.cpp:834-838`)
   - the plate-type labels (`Tab.cpp:4217-4223`)
   - filament sync from the printer (`Plater.cpp:9307-9309`)

   Each per-extruder array then needs 8 entries.
5. **The device-integration features are probably the weak point, not the slicing.** These are filament sync from the printer, nozzle sync and the U1 "device" page.
   - The C++ side discovers extruders dynamically from Moonraker status keys (`extruder`, `extruder1`…`extruderN`; `SSWCPProtocol.cpp:172-235`) and sizes everything from array lengths (`SSWCP.cpp:1657-1777`, `Plater.cpp:9294-9440`).
   - The Flutter web device UI (`resources/web/flutter_web`) is **not in the repo**, so its slot layout cannot be checked.
   - The only fixed "4" found in the filament-sync GUI is a grid column count used for layout (`FilamentColorMapBoxGroup.cpp:62-68`, 4 or 5 columns, scrollable), not a slot limit.
6. **The printer-side consumers of slicer output appear list-length agnostic.** The Moonraker metadata parser (`u1-moonraker/moonraker/components/file_manager/metadata.py:418,462-579`) reads `;`/`,` separated lists from the Orca footer `CONFIG_BLOCK`. That includes filament_colour, filament_type, filament used [g], nozzle_diameter and filament_retract_length_toolchange. It does not assume 4 entries. Whatever Klipper macros consume these lists (`klippy_apis.py:291-307`) are a firmware-side question.
7. **Ooze and preheat handling is generic Orca and already enabled for U1.**
   - All U1 process presets set `ooze_prevention = 1`. `fdm_process_U1.json:47` sets `standby_temperature_delta = -5`. Some presets set `preheat_time = 30`.
   - The GCodeProcessor inserts look-ahead `M104 S.. Tn` preheats before `Tn` for any tool index (`GCodeProcessor.cpp:714-725,4597-4668`).
   - With 8 tools, idle/standby temperature handling matters more: there are more parked hot nozzles, and the `T0..T3` cooldowns are hardcoded in the start gcode.
8. **Effort estimate:**
   - **Profile only:** about 0.5–1 day. This covers the JSON preset, start gcode, geometry and offsets, plus a slicing smoke test.
   - **Fork GUI/device-sync changes:** 2–5 days, and only if the Flutter UI or the sync dialogs need work beyond what the arrays already handle.
   - The real long pole is firmware: the `SM_*` macros and `T4..T7` need to exist, plus the Moonraker/Klipper metadata consumers. See the other research reports.

---

## 1. U1 machine profiles

### 1.1 Location and inheritance

| File | Role |
|---|---|
| `snapmaker-profiles/Snapmaker.json:8-9` (same in `OrcaSlicer/resources/profiles/Snapmaker.json`) | Declares `machine_model` "Snapmaker U1" → `machine/Snapmaker U1.json`, plus processes `fdm_process_U1` etc. |
| `.../Snapmaker/machine/Snapmaker U1.json` | Model definition: `model_id` `SM_U1`, `nozzle_diameter` "0.2;0.4;0.6;0.8", `bed_model` "Snapmaker U1_bed.stl" |
| `.../machine/fdm_klipper.json` | Base Klipper printer |
| `.../machine/fdm_toolchanger.json` | Inherits fdm_klipper. Generic toolchanger: accel X/Y 20000, max speed X/Y 500, Z 12, E 25; `printable_height` 250; `single_extruder_multi_material` "1" (overridden by U1); empty `change_filament_gcode`; generic `PRINT_START` |
| `.../machine/fdm_U1.json` | Inherits fdm_toolchanger, `instantiation: false`. Sets `single_extruder_multi_material` "0". Has **5-element** per-extruder arrays (e.g. `extruder_offset` all `0x0`, lines 39-45), `purge_in_prime_tower` 0, `change_filament_gcode` "" (line 182). `machine_start_gcode` (line 183) is a Prusa-XL-derived template with T0–T5 `is_extruder_used` branches and purge positions X 0/120/180/300; the concrete variants override it. `version` 2.1.1.1 |
| `.../machine/Snapmaker U1 (0.2 nozzle).json`, `(0.4 nozzle)`, `(0.6 nozzle)`, `(0.8 nozzle)` | Concrete, instantiable presets. `setting_id` SM_U1, inherit `fdm_U1`, **4-element** per-extruder arrays. All four have the same change_filament_gcode (date 20261003) |

Process: `process/fdm_process_U1.json` (`standby_temperature_delta` -5 at line 47, `enable_prime_tower` 0, `prime_tower_width` 60). `process/fdm_process_U1_common.json` sets `enable_prime_tower` 1 (line 71), `prime_tower_width` 35, `travel_speed` 500, `exclude_object` 1, `wipe_tower_no_sparse_layers` 0, and a `filename_format` using `filament_type[initial_tool]`.

Filaments: for example, `filament/Snapmaker PLA Basic @U1.json` has `"compatible_printers": ["Snapmaker U1 (0.4 nozzle)"]`. A user printer preset inheriting from that system preset still sees these filaments (`Preset.cpp:754-784`, `is_compatible_with_parent_printer`).

### 1.2 Key values in `Snapmaker U1 (0.4 nozzle).json`

| Setting | Value |
|---|---|
| Extruder count | 4 (array length of `nozzle_diameter`, lines 65-70: `0.4` ×4) |
| `extruder_offset` | `0x0` ×4 (lines 24-29). The firmware applies the tool offsets, not the slicer |
| `printable_area` | `0.5x1, 270.5x1, 270.5x271, 0.5x271` (≈270 × 270 mm) |
| `printable_height` | 270.05 |
| `machine_max_speed_z` | [20, 12]; `machine_max_speed_e` [30, 25]; `machine_max_jerk_z` [3, 0.4] (X/Y accel and speed limits from fdm_toolchanger: 20000 / 500) |
| `machine_tool_change_time` | 5 s (used for time estimates; `PrintConfig.cpp:2156`) |
| `tool_change_temprature_wait` | 0 (`PrintConfig.cpp:2165`, default true) |
| `retract_length_toolchange` | 10 ×4; `retraction_length` 1.5; `z_hop` 0.4 (Auto Lift); `wipe_distance` 2 |
| `extruder_clearance_radius` | 72.5; `extruder_clearance_height_to_rod` 27.5 |
| `nozzle_volume` | 143; `nozzle_type` hardened_steel |
| `printer_flow_support` | ["standard", "high_flow"] (Snapmaker flow variants) |
| `host_type` | octoprint (Moonraker-compatible upload) |
| `thumbnails` | "48x48/PNG, 300x300/PNG" |
| `machine_pause_gcode` | M600 |
| `before_layer_change_gcode` | includes `TIMELAPSE_TAKE_FRAME`, `DEFECT_DETECTION_DETECT` |
| `layer_change_gcode` | `SET_PRINT_STATS_INFO TOTAL_LAYER=... CURRENT_LAYER=...` |

(The JSON strings use `\\n` escapes, which ConfigOptionString deserialisation unescapes.)

### 1.3 `machine_start_gcode` (line 51, date 20260128): where 4 tools are hardcoded

Sequence:
1. `PRINT_START`, `DEFECT_DETECTION_START`, `SET_PRINT_STATS_INFO`, `TIMELAPSE_START`
2. `M140`, `M104 T{initial_extruder} S140`, `SET_PURIFIER_MODE` (by chamber_cooling_mode)
3. `G28 X Y`, `DEFECT_DETECT_NOODLE_FIRST`, `T{initial_extruder}`, `DEFECT_DETECTION_DETECT_BED`, `SM_PRINT_CHECK_SWITCH_EXTRUDER`
4. The **hardcoded per-tool block**:
   ```
   SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=1 TEMP=140
   SM_PRINT_AUTO_FEED EXTRUDER=0
   SM_PRINT_FLOW_CALIBRATE EXTRUDER=0
   SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=2 TEMP=140
   SM_PRINT_AUTO_FEED EXTRUDER=1
   SM_PRINT_FLOW_CALIBRATE EXTRUDER=1
   SM_PRINT_EXTRUDER_PREHEAT EXTRUDER=3 TEMP=140
   SM_PRINT_AUTO_FEED EXTRUDER=2
   SM_PRINT_FLOW_CALIBRATE EXTRUDER=2
   SM_PRINT_AUTO_FEED EXTRUDER=3
   SM_PRINT_FLOW_CALIBRATE EXTRUDER=3
   M104 S0 T0 A0
   M104 S0 T1 A0
   M104 S0 T2 A0
   M104 S0 T3 A0
   ```
   This block is pipelined: it preheats tool n+1 while it feeds and calibrates tool n.
5. `SM_PRINT_PREEXTRUDE_FILAMENT INDEX={initial_extruder}`, `MOVE_TO_DISCARD_FILAMENT_POSITION`, `ROUGHLY_CLEAN_NOZZLE_WITH_DISCARD`, `MOVE_TO_XY_IDLE_POSITION_EXTRUDER`
6. `G28 Z I140 J140`, `DETECT_BED_PLATE`, `FINELY_CLEAN_NOZZLE_STAGE_1/2`, `WAIT_CHAMBER_TEMP`
7. `G28 Z` (with `Z_OFFSET -0.07` for the High Temp / Graphic Effect plate), `BED_MESH_CALIBRATE PROBE_COUNT=11,11`
8. Purge line `G0 X85 Y1` → `G1 X185 E15`

`machine_end_gcode`: lifts Z for by-object prints, then `PRINT_END`, `TIMELAPSE_STOP`.

### 1.4 `change_filament_gcode` (line 11, unescaped, date 20261003)

```
;===== date: 20261003 =====================
; Change Tool[previous_extruder] -> Tool[next_extruder] (layer [layer_num])
; max_layer_z [max_layer_z]
; max_print_height [max_print_height]
; print_sequence [print_sequence]
{
local move_z = 1.5;
local max_speed_toolchange = 350.0;
local wait_for_extruder_temp = true;
position[2] = position[2] + 2.0;
local speed_toolchange = max_speed_toolchange;
if travel_speed < max_speed_toolchange then speed_toolchange = travel_speed; endif
if print_sequence == "by object" then
    move_z = max_print_height;
    if max_layer_z < ((max_print_height - z_offset) - 2) then
        move_z = z_offset + min(((max_layer_z - z_offset) + 2), max_print_height);
    endif
"G90\nG1 Z" + move_z + " F600\n";
else
"G91\nG1 Z" + move_z + " F600\nG90\n";
endif
"G1 F" + (speed_toolchange * 60) + "\n";
if wait_for_extruder_temp and not((layer_num < 0) and (next_extruder == initial_tool)) then
      "\n"; "; " + layer_num + "\n";
      if layer_num == 0 then "M104 S" + first_layer_temperature[next_extruder] + " T" + next_extruder + "\n";
      else "M104 S" + temperature[next_extruder] + " T" + next_extruder + "\n"; endif
endif
"M400" + "\n";
"T" + next_extruder + "\n";
if filament_type[next_extruder] == "PVA" then "SET_VELOCITY_LIMIT ACCEL=3000\n"; else endif
if previous_extruder != next_extruder and initial_extruder != next_extruder then
"SM_PRINT_PREEXTRUDE_FILAMENT INDEX=" + next_extruder + "\n";
endif
"G90\n";
}
```

Because this gcode emits `T`, the slicer does **not** add its own `Tn` (`GCode.cpp:9239-9244`, `custom_gcode_changes_tool`). The template is tool-count agnostic. The printer only has to support `T4`..`T7` and `SM_PRINT_PREEXTRUDE_FILAMENT INDEX=4..7`.

---

## 2. Multi-extruder handling in the fork

| Item | Location | Note |
|---|---|---|
| Max extruders / filaments | `libslic3r.h:65,68` | 64 / 64 |
| GUI extruder count spin | `Tab.cpp:5173-5178` | `max = MAXIMUM_EXTRUDER_NUMBER` |
| Extruder count derivation | `Preset.cpp:384-402` | `set_num_extruders(nozzle_diameter.size())` when not SEMM |
| Filament count sync on extruder count change | `Tab.cpp:2240-2266` | U1 special case (line 2251): if the preset name contains "Snapmaker U1" and there are more filaments than extruders, the filament count is kept (supports mixed/virtual filaments) |
| `is_extruder_used[]` placeholder | `GCode.cpp:2939-2940`, `PrintConfig.cpp:9006` | Sized `max(64, filament count)`. Safe for 8 |
| U1 detection | `WipeTower2.cpp:1325` | `boost::icontains(m_printer_model,"Snapmaker") && icontains(...,"U1")` |
| U1 wipe tower speed handling | `WipeTower2.cpp:998-1013` | Emits `M220 B` / `M220 R` around tower moves |
| U1 tower interface UI | `ConfigManipulation.cpp:834-838`; `Tab.cpp:3186,3617,4529` | Gated on printer_model containing "Snapmaker U1" |
| U1 plate label | `Tab.cpp:4217-4223` | "Cool Steel Plate" naming |
| U1 color memory | `Tab.cpp:6161` | `remember_printer_config` |
| Default printer model | `PresetBundle.cpp:238` | `SM_DEFAULT_PRINTER_MODEL = "Snapmaker U1"` |
| Device model normalisation | `SSWCPProtocol.cpp:158-170` | "lava" / "Snapmaker test" → "Snapmaker U1" |
| Nozzle info from device | `SSWCPProtocol.cpp:172-235` | Iterates `extruder`, `extruder1`… dynamically, with **no 4-tool cap**. Supported diameters are only 0.2/0.4/0.6/0.8 (lines 18-34) |
| Nozzle sync / sync button | `Plater.cpp:2227,3633,3901` | Only when model == "Snapmaker U1" |
| Filament sync from printer | `Plater.cpp:9294-9440` | Whitelist `{"Snapmaker U1"}` (9307-9309); otherwise rejects with "The connected printer is not U1". Filament count is sized from the synced list (limit 64) |
| Machine filament parsing | `SSWCP.cpp:1657-1777` | Loops over `filament_official`, `extruder_map_table` and `nozzle_diameters` by array length |
| Send mapping to device | `SSWCP.cpp:3354-3482` | Sends colors, types, weights and `filament_extruder_map`; length-driven |
| Sync dialog layout | `GUI/filamentsync/FilamentColorMapBoxGroup.cpp:62-68` | 4 or 5 grid columns depending on language. Layout only, scrollable |
| U1 device page | `Plater.cpp:15793` | Loads `flutter_web/index.html?path=2`. **Not in repo**; cannot verify the slot count |
| Mixed (virtual) filaments | `PrintConfig.cpp:4371-4467`, `2081` | `mixed_filament_*`, `filament_multi_colors`. Not tied to 4 |

A grep for `== 4`, `< 4`, `[4]` and similar near extruder/filament/tool in `src/slic3r/GUI` and `src/libslic3r` found **no hardcoded 4-tool constants** in the slicing or sync logic.

---

## 3. Gcode output conventions the printer depends on

### 3.1 Tool selection
- `T<n>` is emitted by the custom `change_filament_gcode`. It is preceded by `M104 S<temp> T<n>` and `M400`, and followed by `SM_PRINT_PREEXTRUDE_FILAMENT INDEX=<n>` (skipped for the initial tool).
- The start gcode issues `T{initial_extruder}` explicitly.
- `GCodeProcessor::process_line_T` (`GCodeProcessor.cpp:4597-4668`) clamps tool numbers that exceed the configured extruder count. With a 4-element profile, a T5 would be flagged and invalid, which is why the arrays must be sized to 8.

### 3.2 Ooze prevention and preheating (generic Orca)
- `OozePrevention::pre_toolchange` / `post_toolchange` (`GCode.cpp:258-290`). Before the change it emits a standby cooldown `M104 ... ;cooldown` for the outgoing tool (`standby_temperature_delta`, `PrintConfig.cpp:5181`). After the change it emits `M104` or `M109` for the incoming tool, depending on `tool_change_temprature_wait`.
- Preheat look-ahead (`GCodeProcessor.cpp:714-725`) is enabled when `preheat_time > 0`, the printer is not SEMM, and there is more than one extruder. It back-inserts `M104 S.. Tn ; preheat Tn time: Xs` before the tool change (`PrintConfig.cpp:5193` preheat_time default 30, max 120; `5204` delta_temperature; `5215` preheat_steps). The `M104.1` variant is used only for the Prusa XL (`is_XL_printer`).
- U1 process presets have `ooze_prevention = 1` (all "... @Snapmaker U1 (...)" process files) and `preheat_time = 30` in "0.20mm Standard/High Quality @Snapmaker U1 (0.4 nozzle)" (lines 20-21).
- Some filament categories (ASA/ABS/PA-CF/PCTG) carry an `idle_temperature`.

### 3.3 Prime tower
- `WipeTower2` (the non-BBL tower, `WipeTower2.hpp:1` "support all MMU device and toolchanger") is used. `enable_prime_tower` is 1 in `fdm_process_U1_common.json:71`.
- The tower adds U1 `M220 B/R`. `purge_in_prime_tower` is 0 at machine level. Its size scales with the number of tools used and is independent of the configured total.

### 3.4 Header and footer metadata (parsed by Moonraker)
- `HEADER_BLOCK` (`GCode.cpp:2638-2686`) contains filament_density, filament_diameter and max_z_height.
- The non-BBL footer (`GCode.cpp:3499-3524`) contains total filament used [g], cost, total filament change, total layers count, and the `CONFIG_BLOCK_START…END` full config dump. That includes all per-extruder arrays: first_layer_bed_temperature, bed_shape, first_layer_temperature, first_layer_height.
- Moonraker (`u1-moonraker/.../metadata.py:418` SnapmakerOrca regex; `462-579`) extracts filament_colour, filament_multi_colors, filament_colour_mode, filament used [g]/[mm], filament_type, filament_volume_type, process_flow_support, print_sequence, filament_retract_length_toolchange, filament_settings_id and the nozzle_diameter list. All are split dynamically, with no fixed count.
- `klippy_apis.py:291-307` passes these lists (nozzle_diameter_list, filament_type split on `;`, filament_used_g …) to a Klipper-side script. **Whether that script assumes 4 entries is a firmware question.**
- Other in-print commands: `SET_PRINT_STATS_INFO`, `TIMELAPSE_*`, `DEFECT_DETECTION_*`, `EXCLUDE_OBJECT_*` (exclude_object=1). None of these are per-tool.

---

## 4. What an 8-tool U1 profile needs

### 4.1 Profile-only route (no slicer code changes)

Create a **user printer preset** (or a vendor-style JSON in the bundle) that:

1. `inherits: "Snapmaker U1 (0.4 nozzle)"`. Keep `printer_model: "Snapmaker U1"` and put "Snapmaker U1" in the preset name (e.g. "Snapmaker U1 8T (0.4 nozzle)"). Keeping the name preserves the U1 code paths (wipe tower M220, tower interface, sync whitelist, Tab.cpp filament count logic).
2. Gives **8-element arrays** for every per-extruder option. Orca re-sizes missing entries from the first value (`set_num_extruders`), but setting them explicitly is safer. The options are:
   - `nozzle_diameter`, `extruder_offset`, `extruder_colour`
   - `retract_length_toolchange`, `retract_restart_extra_toolchange`
   - `retraction_length`, `retraction_speed`, `deretraction_speed`, `retract_restart_extra`, `retract_before_wipe`, `retract_when_changing_layer`, `retraction_minimum_travel`
   - `wipe`, `wipe_distance`
   - `z_hop`, `z_hop_types`, `retract_lift_above`, `retract_lift_below`, `retract_lift_enforce`
   - `min_layer_height`, `max_layer_height`
   - `default_filament_profile`, `nozzle_volume` (if vectorised in this fork)
   - `printer_flow_support`-related per-extruder data (if any)
   - `machine_max_*` (these are 2-element normal/stealth arrays and do **not** scale with the extruder count)
3. **Start gcode:** extend the per-tool block to EXTRUDER 4..7 and `M104 S0 T4..T7 A0`. Better, rewrite it as a guarded loop-equivalent, for example:
   ```
   {if is_extruder_used[4]}SM_PRINT_AUTO_FEED EXTRUDER=4
   SM_PRINT_FLOW_CALIBRATE EXTRUDER=4{endif}
   ```
   This avoids preheating and calibrating 8 tools when only 2 are used. Orca's placeholder language has no `for` loop, so the guards must be unrolled.
4. **Geometry:**
   - Revisit `printable_area` and `printable_height` if the second-row docking reduces the usable bed or Y range.
   - Revisit `extruder_clearance_radius` / `extruder_clearance_height_to_rod` if the carriage changes.
   - Keep `extruder_offset` at 0x0 if the firmware applies per-tool offsets (as the stock U1 does).
5. **Timing:** raise `machine_tool_change_time` if second-row docks are slower to reach. This only affects time estimates.
6. **Filaments:** user printer presets inherit compatibility from the parent system printer (`Preset.cpp:754-795`), so the `@U1` filament presets remain selectable. A new vendor printer preset would instead need its name added to each filament's `compatible_printers`, or a `compatible_printers_condition`.
7. **Process:** reuse the U1 processes. Consider increasing `preheat_time` and keeping `ooze_prevention` with a larger negative `standby_temperature_delta`, because more tools are parked.

### 4.2 When fork code changes would be needed
- **Device integration:** if the Flutter device page or the filament-sync dialog assumes 4 slots (the Flutter part is not in the repo), or if the firmware reports a different machine model string. A different string would be rejected by `Plater.cpp:9307-9309`, so the firmware should keep reporting "Snapmaker U1" or the whitelist must be extended.
- **Bundled vendor profile:** a proper "Snapmaker U1 8T" printer would need a new `machine_model` entry in `Snapmaker.json`, cover and bed images, and filament `compatible_printers` updates.
- **Model-name checks:** any code keyed on the exact model name `== "Snapmaker U1"` (`Plater.cpp:2227`) would need extending if the model is renamed.

### 4.3 Effort estimate

| Work item | Effort |
|---|---|
| User JSON preset (8-wide arrays, start gcode rewrite, geometry tweaks) | 0.5–1 day |
| Validation: slice 8-colour test, inspect T0–T7, preheat M104s, footer CONFIG_BLOCK, Moonraker metadata | 0.5 day |
| Bundled vendor profile in fork (new model, images, filament compat) | 1–2 days |
| GUI / device-sync / Flutter adaptation (if needed) | 2–5+ days (unknown; Flutter source unavailable) |
| Firmware-side: SM_* macros for EXTRUDER 4–7, T4–T7, metadata consumers | Out of scope here; see the firmware reports. This is the dominant cost |

---

## 5. Upstream OrcaSlicer toolchanger support worth reusing

- **Generic toolchanger base (`fdm_toolchanger.json`)** is already the U1's ancestor. It provides non-SEMM multi-extruder behaviour, `ooze_prevention`, `preheat_time` look-ahead and `WipeTower2`, and works for any number of tools.
- **Prusa XL (5 tools):**
  - The start gcode in `fdm_U1.json:183` is visibly derived from it. Note its T0–T5 `is_extruder_used` branches and per-tool purge positions.
  - This is the best template for **guarded, per-tool start gcode** and is the pattern to copy for T0–T7.
  - Orca also has XL-specific `M104.1` predictive preheat (`GCodeProcessor.cpp` `is_XL_printer`). It is not usable by Klipper without a matching macro.
- **Community Klipper toolchangers (TapChanger / StealthChanger / Klipper-toolchanger profiles in upstream Orca):** these use `T<n>` macros on the printer with offsets applied in firmware, an empty or minimal `change_filament_gcode`, and `ooze_prevention` with standby temperatures. That model matches the U1 approach and supports arbitrary tool counts. Many users run 6–8 tools this way.
- **Bambu H2D:** a dual-nozzle BBL design with BBL-specific code paths (`is_BBL_printer`, `filament_map`, `nozzle volume types`). It is not reusable for U1, which uses the non-BBL paths.

---

## Open questions

1. Does the U1 Klipper firmware (or a modified one) accept `T4`–`T7`, and do `SM_PRINT_AUTO_FEED`, `SM_PRINT_FLOW_CALIBRATE`, `SM_PRINT_EXTRUDER_PREHEAT` and `SM_PRINT_PREEXTRUDE_FILAMENT` accept EXTRUDER/INDEX 4–7? See the Klipper/firmware reports.
2. Does the Klipper-side script fed by `klippy_apis.py:291-307` (filament_type, nozzle_diameter_list, filament_used_g) assume 4 entries, for example for RFID/filament-slot mapping or the print-start filament check `SM_PRINT_CHECK_SWITCH_EXTRUDER`?
3. Does the Flutter device UI (`resources/web/flutter_web`, not in the repo) and the touchscreen UI render more than 4 slots? Can `filament_extruder_map` values ≥4 be handled by the printer?
4. What model string would a modified printer report over SSWCP/Moonraker? It must stay "Snapmaker U1" for filament and nozzle sync to work without fork changes.
5. Second-row geometry: does the second row of docks reduce the printable Y range or require a different `printable_area`, purge/discard position, or idle position (`MOVE_TO_XY_IDLE_POSITION_EXTRUDER`)?
6. Is `nozzle_volume` (and the flow-variant data from `printer_flow_support`) vectorised per extruder in this fork's U1 config, and should the second-row tools differ (e.g. different hotends)?
7. Start-up time: calibrating 8 tools sequentially (auto-feed plus flow calibration) may add several minutes. Should calibration run only for `is_extruder_used` tools? This depends on firmware semantics.
