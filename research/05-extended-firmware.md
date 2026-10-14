# 05 - SnapmakerU1-Extended-Firmware: build, architecture, toolheads, and deploying an 8-tool experiment

Source analysed (read-only clone): `C:\Users\N\u1-second-row\refs\SnapmakerU1-Extended-Firmware`
(upstream: https://github.com/paxx12-snapmaker-u1/SnapmakerU1-Extended-Firmware). The clone is shallow (one commit), so there is no git history.
Cross-referenced against: `C:\Users\N\u1-second-row\refs\u1-klipper` (Snapmaker's Klipper fork, including `lava/printer.cfg`).

All paths below are relative to the extended-firmware clone unless they start with `refs/u1-klipper/` or are absolute.

---

## Key findings

1. **Firmware images are not cryptographically signed.**
   - The `.bin` upgrade file is an "UPFILE" container with magic `SNMK`.
   - The header and entries are obfuscated with a fixed 256-byte substitution table and protected only by a 16-bit additive checksum plus a per-entry MD5 (`tools/upfile/upfile.c:16-49`, `tools/upfile/helpers.h:59-170`).
   - Custom images install through the stock **Settings > About > Firmware Version > Local Update** from a FAT32 USB stick (`docs/install.md:23-32`).
   - No exploit and no bootloader unlock is needed.
2. **Building is a reproducible unpack, overlay, repack pipeline.**
   - It runs in Docker (`./dev.sh make build PROFILE=extended[-<mod>]`).
   - It downloads a pinned stock firmware (`vars.mk:1-3`, stock 2.0.0.205), unsquashes the rootfs, and applies ordered overlays (patches, file copies, scripts).
   - It then rebuilds the squashfs (zstd) and the Rockchip `update.img`, and re-wraps the result as an UPFILE (`scripts/create_firmware.sh:59-136`).
3. **The U1 is a Rockchip RK3562 Linux host running Snapmaker's fork of Klipper, Moonraker and Fluidd/Mainsail, plus closed-source binaries.**
   - The closed binaries are `/usr/bin/gui` (the touchscreen UI), `unisrv` (cloud, camera and OTA) and `lmd` (the launcher).
   - The host has one main MCU (AT32F403A on `/dev/ttyS6` at 921600 baud).
   - Each toolhead has its own MCU (`e0`..`e3`, USB CDC, VID:PID 1d50:614e) on fixed USB hub ports `1.3, 1.4, 1.2, 1.1` (`refs/u1-klipper/lava/printer.cfg:9-28`).
4. **Klipper is stored as editable Python source** at `/home/lava/klipper`, and the factory config at `/home/lava/origin_printer_data/config/printer.cfg`. Overlays can do all of the following, and the project already does each one:
   - patch Klipper Python with `.patch` files;
   - drop in new or replacement `klippy/extras/*.py` modules;
   - patch the factory `printer.cfg` and `fluidd.cfg`.

   The extended firmware also adds `[include extended/klipper/*.cfg]` to `printer.cfg`. Any section, including `[extruder]` and `[mcu eN]`, can then be overridden from a user file **without rebuilding firmware**.
5. **The 4-tool limit appears in several layers.**
   - Klipper config: `max_physical_extruder_num: 4` (`refs/u1-klipper/lava/printer.cfg:115`), enforced at `refs/u1-klipper/klippy/toolhead.py:247-248,696`.
   - One `[park_detector extruderN]` per tool, using 4 ADC pins on the main MCU (PB0, PC4, PC5, PB1).
   - Feeders: 2 `filament_feed` modules × 2 channels.
   - NFC: 2 `fm175xx` readers × 2 channels.
   - Toolhead USB: 4 hub ports.
   - The closed GUI and `unisrv` almost certainly assume 4 tools as well.
   - The extended firmware's own scripts hardcode 4 toolheads too (e.g. `S59toolhead-sim:19` `TOOLHEADS="1:e0 2:e1 3:e2 4:e3"`).
6. **There is a toolhead MCU simulator** (`overlays/firmware-extended/41-feature-toolhead-mcu-simulator`). It runs host-side "dummy" Klipper MCUs on ptys `/tmp/klipper_host_eN`.
   - This is the best tool for testing an 8-tool Klipper config (`[mcu e4]`..`[mcu e7]`) **before any hardware exists**.
   - Running in qemu (`scripts/dev/qemu.sh`) also works, or running klippy by hand (`scripts/dev/run-klipper.sh`).
7. **Recovery is robust.**
   - The device has A/B rootfs slots (`updateEngine --misc=other --reboot` switches slot).
   - The firmware-config web UI offers "Switch/Reset to Backup Firmware".
   - USB recovery trigger files exist (`extended-recover.txt`, `full-recover.txt`).
   - You can always reflash a stock `.bin` via Local Update.
   - SSH access is root/snapmaker and lava/snapmaker.
8. **No local evidence was found of community work on more than 4 toolheads.** Online search (GitHub issues, Discord) could not be performed in this session; see Open questions.
9. **Recommended path.**
   - First, an extended-firmware build plus a **personal mod overlay** (`overlays/mods/<user>/`).
   - Iterate with `extended/klipper/*.cfg` overrides and `scripts/dev/upgrade-rootfs.sh`, which needs no reflash.
   - Validate 8-tool logic against simulated MCUs before connecting real toolheads.
   - Plan from the start on HelixScreen or the web UI rather than the stock touchscreen GUI.

---

## 1. Build, unpack/repack, overlays, signing, install, root access, recovery

### 1.1 Toolchain
- **Docker image:** `.github/dev/Dockerfile:5-43`.
  - Based on Debian trixie.
  - Includes `squashfs-tools`, `g++-aarch64-linux-gnu`, `dos2unix`, `u-boot-tools`, `golang-go`, `ffmpeg`, `sshpass`, `ccache`, and arm64 `libssl-dev`.
- **Wrapper:** `./dev.sh` runs commands inside that image (`docs/development.md`).
- **CI:** builds on `ubuntu-24.04-arm` (`.github/workflows/pull_request.yaml:13`):
  - `./dev.sh make firmware` (download stock);
  - `./dev.sh make build PROFILE=extended OUTPUT_FILE=...` (`pull_request.yaml:85-97`);
  - `PROFILE=extended-afc` is also built.
- **Pinned inputs** (`vars.mk:1-6`):
  - `FIRMWARE_FILE=U1_2.0.0.205_20260914173503_upgrade.bin`, `FIRMWARE_VERSION=2.0.0`, with a SHA256 check;
  - kernel `rockchip-linux/kernel` @ `8533b2249e1550b233a4836d039d64e3bb2fed7a`, version 6.1.99. This kernel is used only to build extra modules, e.g. `overlays/firmware-extended/10-patch-kernel-modules/scripts/01_compile_kernel_modules.sh`.
- **Makefile** (`Makefile:14-21,38,71-75`):
  - parses `PROFILE=<firmware>[-<mod>...]`;
  - downloads the stock firmware from `public.resource.snapmaker.com`;
  - also offers `make extract` (unpack only) for inspection.

### 1.2 Container format and unpack/repack
- **Outer layer: UPFILE** (`tools/upfile/upfile.c`).
  - Header struct at lines 16-24: magic, magic_ver, checksum, version[24], build_date[14], files, reserved.
  - Entry struct at lines 26-32: type, checksum, offset, size, md5[16].
  - It holds 4 entries (lines 37-49):

    | Type | File |
    |---|---|
    | `SOC_FW` | `update.img` |
    | `MCU1_FW` | `at32f403a.bin` (main board MCU) |
    | `MCU2_FW` | `at32f415.bin` (toolhead MCU, see 3.1) |
    | `MCU_DESC` | `MCU_DESC` |

  - Header and entries are byte-substituted (`helpers.h:59-114`), with a 16-bit sum checksum (`helpers.h:136-157`) and an MD5 per file (`helpers.h:159-170`).
  - **There is no signature or key anywhere.** `pack` regenerates everything (`upfile.c:255-311`).
- **Inner layer: Rockchip image.**
  - Unpack: `scripts/helpers/unpack_firmware.sh:30-37` runs `upfile unpack`, then `img_unpack update.img rk-loader.img rk-rom.img`, then `afptool -unpack rk-rom.img rk-unpacked`.
  - Repack: `scripts/helpers/pack_firmware.sh:30-36` reverses this.
  - Partitions include `rk-unpacked/rootfs.img` (squashfs), `boot.img` and `misc.img`.
- **Rootfs rebuild** (`scripts/create_firmware.sh:59-136`):
  - Must run as root, to preserve ownership.
  - Runs `unsquashfs`, then the overlay loop (lines 76-111), then the sanity checks:
    - ownership is preserved, e.g. `/home/lava/bin/hwver.sh` must stay uid 1000;
    - any non-ARM ELF dropped into the rootfs is rejected.
  - Then runs `mksquashfs -comp zstd`.
  - Appends the git revision to `UPFILE_VERSION` (line 133), then repacks.
- **Note:** the MCU firmware blobs (`at32f403a.bin`, `at32f415.bin`) pass through unmodified. The project does not rebuild the main or toolhead MCU firmware.

### 1.3 Overlays
- **Order of application** (`Makefile`, `scripts/create_firmware.sh:76-111`):
  1. `overlays/common/*`
  2. `overlays/firmware-<profile>/*` (e.g. `firmware-extended`, numbered `NN-name` dirs, applied in lexical order)
  3. `overlays/mods/<mod>/*`
- **Order within each overlay directory:**
  1. `pre-scripts/*.sh` (run with the rootfs path as `$1`)
  2. `patches/**.patch`. The patch path mirrors the rootfs path (e.g. `patches/home/lava/klipper/...`) and is applied with `patch -F0 -p1`, so there is **zero fuzz**. Patches break loudly if stock changes.
  3. `root/`, copied over the rootfs with `cp -rv`. This adds or replaces files.
  4. `scripts/*.sh` (post-scripts; may cross-compile, e.g. the toolhead simulator build).
- **Personal mods** live in `overlays/mods/<username>/` and are selected via `PROFILE=extended-<username>`. They are not shipped in releases (`docs/development.md`).
- **Existing mods:** `afc` (AFC-Lite plus CAN), `devel` (Entware), `paxx12` (camera AI), `qemu`.

### 1.4 Installation
- **USB install:**
  - Copy the `.bin` to a FAT32 USB stick.
  - Go to Settings > About > Firmware Version > Local Update (`docs/install.md:23-32`).
  - To revert, flash a stock `.bin` the same way (`docs/install.md:45-58`).
- **Install over SSH (dev):**
  - `scripts/dev/upgrade-firmware.sh` builds the firmware and `scp`s `tmp/firmware/update.img` to `/userdata/`.
  - It then runs `/home/lava/bin/systemUpgrade.sh upgrade soc <file>`. That command writes the SoC image to the inactive A/B slot.
  - `systemUpgrade.sh upgrade all` also flashes the MCUs (`overlays/firmware-extended/02-firmware-config/.../functions/30_upgrade.yaml:63,109`).
- **Fast iteration without flashing:** `scripts/dev/upgrade-rootfs.sh` tars the overlays' `root/` trees and extracts them straight onto the live `/` over SSH.
  - It needs a writable overlayfs. Persistence requires `/oem/.debug`, see 1.6.
  - It does not apply `patches/`.
- **OTA from the web UI:** firmware-config "Upgrade" accepts a URL or an upload (`docs/firmware_config.md`, `30_upgrade.yaml`). Stock `unisrv` checks MD5 on OTA downloads (`docs/functions/README.md:115`).

### 1.5 Root and SSH access
- **Credentials:** `root` / `snapmaker` and `lava` / `snapmaker` (`docs/ssh_access.md`).
- **Two ways to enable SSH:**
  - Stock firmware 1.2.0 and later has a GUI "Root Access" toggle.
  - The extended firmware removes the `custom_misc vertype == dbg` gate in `/etc/init.d/S50dropbear` (`overlays/common/02-enable-ssh/patches/01-enable-ssh.patch`).
- **Debug misc image:** `tools/debug/debug_misc.img` with `scripts/enable_debug_misc.sh` can swap in a debug `misc.img`.

### 1.6 Persistence and recovery
- **Read-only root:** the rootfs is read-only squashfs with an overlayfs on top (`/etc/init.d/S01aoverlayfs`).
  - Changes to `/` persist only if `/oem/.debug` exists (`docs/data_persistence.md`).
  - A firmware upgrade wipes those persisted changes.
- **Printer config:**
  - Runtime config lives in `/home/lava/printer_data/config` (= `/oem/printer_data/config`) and persists.
  - It is seeded from `/home/lava/origin_printer_data/config` when `/oem/.printer_data` is missing (`S48setup-lava-env`).
  - Therefore an overlay that patches the *origin* `printer.cfg` only takes effect after a config reset, or if the runtime copy is updated by hand.
- **A/B slots:**
  - The kernel cmdline carries `android_slotsufix=_a|_b`.
  - Slot detection: `functions/01_status_system.yaml:16`.
  - To switch: `updateEngine --misc=other --reboot` (`functions/20_actions_troubleshooting.yaml:12-13,55,68`); `systemUpgrade.sh show-status` reports state.
- **Firmware-config web UI** (`/firmware-config/`, needs Advanced Mode): "Switch to Backup Firmware" and "Reset to Backup Firmware" (`docs/firmware_config.md:17-30,272-322`).
- **USB recovery files:** `extended-recover.txt` (reset extended config) and `full-recover.txt` (full reset), handled by `overlays/firmware-extended/02-firmware-config/root/etc/init.d/S49extended-config:17-38`.
- **Last resort:** flash stock firmware via Local Update.

---

## 2. U1 system architecture (as seen from the rootfs)

| Layer | Detail | Evidence |
|---|---|---|
| SoC | Rockchip RK3562 (aarch64) | `docs/panda_breath.md:41`, rk2918 tools, kernel tree |
| Kernel | 6.1.99 (rockchip-linux) | `vars.mk:4-6` |
| Init | Buildroot SysV: `S01aoverlayfs`, `S48setup-lava-env`, `S49extended-config` (ext), `S50dropbear`, `S59toolhead-sim` (ext), `S60klipper`, `S61moonraker`, `S90lmd` | overlay patches and `root/etc/init.d` files |
| Service hooks (ext) | `/etc/hooks/{klipper.d,moonraker.d,lmd.d}/*.sh`, sourced by the init scripts | `overlays/firmware-extended/01-system-utils/patches/01-add-service-hooks.patch`, `docs/design/service_hooks.md` |
| Motion | Klipper (Snapmaker fork, Python source at `/home/lava/klipper`; some files are CRLF) | `overlays/firmware-extended/11-patch-klipper/`, `13-patch-rfid/pre-scripts/01_klippy_fix_lf.sh` |
| Host MCU | `klippy_mcu` (Linux process MCU, gpiochip0) at `/home/lava/firmware_MCU/klippy_mcu` | `refs/u1-klipper/.../klippy_mcu_config` |
| API/Web | Moonraker (`/home/lava/moonraker`), Fluidd or Mainsail behind nginx | `overlays/firmware-extended/*fluidd*`, `*mainsail*` |
| UI / cloud | `lmd` launches `/usr/bin/gui`, `unisrv` and `flow_calc_server`; all closed-source; configs in `/etc/unisrv/` | `overlays/firmware-extended/40-feature-upgrade-firmware/apps/firmware-imposter/README.md` |
| Power / IO | `lava_io set MAIN_MCU_POWER=1 HEAD_MCU_POWER=1` | init scripts |
| Upgrade | `/home/lava/bin/systemUpgrade.sh`, `updateEngine` | `functions/20_actions_troubleshooting.yaml`, `30_upgrade.yaml` |
| Alt UI (ext) | HelixScreen, bind-mounted over `/usr/bin/gui` | `overlays/firmware-extended/69-app-helixscreen/root/etc/hooks/lmd.d/30-helixscreen.sh` |

**MCU firmware.**
- Main MCU (AT32F403A): Klipper over UART at 921600 baud; `INITIAL_PINS` includes `!PE15`.
- Toolhead MCU (AT32F415): Klipper over USB serial; `INITIAL_PINS="PB2,!PB5,PB0,!PB3"`. Those pins hold the stepper disabled, heater off and fans in their safe state at boot.
- Source: `refs/u1-klipper` board configs `at32f403a_config` and `at32f415_config`.

---

## 3. Printer config and the 4 toolheads

All from `C:\Users\N\u1-second-row\refs\u1-klipper\lava\printer.cfg` (1365 lines). The same file ships as `/home/lava/origin_printer_data/config/printer.cfg`.

### 3.1 MCUs and serial IDs (`printer.cfg:9-28`)
| Klipper MCU | Serial path | USB hub port | Tool |
|---|---|---|---|
| `[mcu]` | `/dev/ttyS6` (921600) | n/a (UART) | main board, AT32F403A |
| `[mcu e0]` | `/dev/serial/by-path/platform-xhci-hcd.0.auto-usb-0:1.3:1.0` | 1.3 | T0 |
| `[mcu e1]` | `...usb-0:1.4:1.0` | 1.4 | T1 |
| `[mcu e2]` | `...usb-0:1.2:1.0` | 1.2 | T2 |
| `[mcu e3]` | `...usb-0:1.1:1.0` | 1.1 | T3 |

- Toolheads are bound **by USB physical path**, not by serial number.
- All toolheads share USB VID:PID `1d50:614e`, the standard Klipper USB ID.
- Consequence for a second row: 4 more toolhead MCUs need either 4 more hub downstream ports or a second hub. The new `by-path` names would then be e.g. `1.5`, or `1.x.y` behind a cascaded hub.
- Discrepancy to note: the extended firmware's simulator binary is named `klipper-dummy-at32f403a`. However, the toolhead pin set and `INITIAL_PINS` match the AT32F415 config, and the UPFILE carries a separate `at32f415.bin`. The likely reading is that the simulator was simply built with the 403A board definition. Needs confirmation (see Open questions).

### 3.2 Kinematic limits (`printer.cfg:107-171`)
- `[printer]`: `max_logical_extruder_num: 32`, `max_physical_extruder_num: 4` (lines 114-115).
- Enforced in `refs/u1-klipper/klippy/toolhead.py:247-248` (read) and `:696`:
  ```python
  if index < self.max_physical_extruder_num or index >= self.max_logical_extruder_num:
  ```
  Logical indices 4..31 are therefore treated as "virtual" mapped extruders. Raising the physical count to 8 changes which indices count as physical versus logical, so every user of these values must be audited.
- Other users of these values: `print_stats.py`, `exclude_object.py`, `pause_resume.py`.
- Axis limits: X `position_max: 271` (line 128), Y `position_max: 335` (line 149), Z `position_max: 275` (line 171).

### 3.3 Dock (park) positions and grab logic
| Tool | Section (line) | `xy_park_position` | `extruder_grab_dir` | Park detector (main MCU ADC) |
|---|---|---|---|---|
| T0 | `[extruder]` (665) | `35.0,332.2` (694) | True | PB0 (`[park_detector extruder]` 720) |
| T1 | `[extruder1]` (830) | `102.7,332.2` (859) | False | PC4 (885) |
| T2 | `[extruder2]` (969) | `170.2,332.2` (998) | False | PC5 (1024) |
| T3 | `[extruder3]` (1107) | `237.7,332.2` (1136) | False | PB1 (1162) |

- **Shared settings:**
  - `y_idle_position: 250`, `fast_move_speed: 400`, `grab_speed: 10`, `switch_accel: 5000`.
  - Dock pitch is 67.5 mm in X.
  - All docks sit at Y = 332.2, inside Y `position_max` 335.
- **Park detectors:**
  - Analog with range 0-470.
  - Each also uses `active_pin: eN:PB1` and `grab_valid_pin: eN:PA3` on the toolhead MCU.
- **Implication for a second row:**
  - Every dock sits at the rear Y limit, and the park detectors use main-board ADC pins.
  - A second row needs new XY park coordinates. These may require extended Y travel or a different docking axis, which is a mechanical question covered in other reports.
  - It also needs either 4 more main-MCU analog inputs or a moved park-detect signal. Using the toolhead MCU's own pins, as `active_pin` and `grab_valid_pin` already do, would be easier.

### 3.4 Per-toolhead pins (identical on e0..e3; `[extruder]` block at 665-826)
- **Stepper:** step `PA8`, dir `PA9`, enable `!PB2`, TMC2209 UART `PA15` at address 3.
- **Thermal:**
  - heater `PB5`, thermistor `PA2` (`NTC_100K_3950_PRECISE`);
  - heat-sw / cut `!PB7`, power-loss sense `PB8`.
- **Fans:**
  - hotend fan `PB3` with tach `PB4`;
  - part (nozzle) fan `!PB0` with tach `PA10`.
- **Sensors:** filament sensor `PA1`, inductance coil `PA0`.
- **e0 only:** accelerometer on `spi1`, cs `PA4` (lis2dw / sc7a20).
- Because the pins are identical, `[extruder4..7]` can be cloned from `[extruder1]` with only the MCU prefix and park values changed.

### 3.5 Filament feeders and RFID
- `[filament_feed left]` (1245) serves channels 1,0; `[filament_feed right]` (1284) serves channels 2,3. Their pins are on the main MCU (PE/PD).
- `_FILAMENT_FEED_VARIABLE` macro: `module_sequence 'left','left','right','right'`, `channel_sequence 1,0,0,1`. **Both are hardcoded 4-element lists.**
- `[fm175xx_reader]` (44): 2 SPI devices × 2 channels, i.e. 4 RFID slots.
- Second-row tools would need new feeders (or manual loading) and new channel maps. Without them, the feed and RFID macros will index out of range.

### 3.6 Macros relevant to tool changes
- Toolchange logic lives in Snapmaker's Klipper extras plus the `printer.cfg` and `fluidd.cfg` macros. Examples: `T0..T3` and `SET_PRINT_EXTRUDER_MAP`, which AFC-Lite wraps.
- The extended firmware's `35-feature-klipper-hooks` patches the `fluidd.cfg` `PRINT_START/END/CANCEL` macros to call `_PRINT_START_*` hooks (`overlays/firmware-extended/35-feature-klipper-hooks/...01-klipper-hooks.patch`).
- `docs/afc-lite.md` maps the 4 extruders to AFC lanes E0-E3 and wraps `AUTO_FEEDING`, `SET_PRINT_EXTRUDER_MAP`, and others.

---

## 4. Overlays that touch toolheads, extruders, Klipper or the UI

| Overlay | What it does | Relevance to 8 tools |
|---|---|---|
| `firmware-extended/02-firmware-config` | Web config UI; `01-add-klipper-includes.patch` appends `[include extended/klipper/*.cfg]` near the end of `printer.cfg` (~line 1261, before SAVE_CONFIG) | **Key enabler**: override or add `[mcu eN]`, `[extruderN]` and `[park_detector ...]` without rebuilding |
| `firmware-extended/11-patch-klipper` | 8 Python patches to `/home/lava/klipper` (upstream backports, snapmaker fix, aht10, temperature_combined) | Pattern for patching `toolhead.py`, `extruder.py` etc. |
| `firmware-extended/13-patch-rfid` | Replaces `filament_protocol_ndef.py`; pre-script runs dos2unix on CRLF klippy files | Shows replacing Snapmaker extras works; CRLF needs care |
| `firmware-extended/31-feature-afc-lite` | Copies `klippy/extras/AFC*.py` | Adding entirely new Klipper modules works |
| `mods/afc/04-patch-klipper/.../01_afc_fix.patch` | Changes `klippy/kinematics/extruder.py` (~line 298) `ExtruderStepper` so an invalid extruder name only warns instead of raising | Shows extruder names are parsed into indices from `extruder[N]`; this parser must accept 4..7 |
| `mods/afc/docs/canbus.md`, `01-rules-canbus` | USB-CAN adapters on `can1` at 1 Mbps; extra MCUs must run Klipper built from Snapmaker/u1-klipper | Alternative transport for extra toolhead MCUs if USB ports run out |
| `firmware-extended/34-feature-faulty-toolhead` | `faulty_toolheadN.cfg` overrides `[extruder] sensor_pin: e0:PC5` etc. via extended include; GUI items per toolhead 1-4 (`24_settings_troubleshooting_faulty_toolhead1.yaml`) | Shows per-tool sections are overridable; hardcoded 1-4 |
| `firmware-extended/41-feature-toolhead-mcu-simulator` | Builds `klipper-dummy-at32f403a` from u1-klipper @ `10f2f697...` (`scripts/01-build-toolhead-sim.sh:7,41-48`); `S59toolhead-sim:14,19,27` spawns one per toolhead on `/tmp/klipper_host_eN`; `faulty_toolheadN_mcu.cfg:13` redirects `[mcu eN] serial:`; `pins.conf` fakes ADC values (PA2=4037, PB1/PA3=4090) | **Simulated e4..e7** for testing an 8-tool config without hardware |
| `firmware-extended/41-feature-generic-purifier` | Patches `home/lava/origin_printer_data/config/printer.cfg` | Template for patching the factory printer.cfg |
| `firmware-extended/38-feature-spoollink` | Adds `spoollink.py` | Another drop-in extra |
| `docs/filament_feeders.md` | Raises `preload_length` limit to 2500 in `filament_feed.py` | Shows `filament_feed.py` is patched; it is a candidate for channel-count changes |
| `firmware-extended/69-app-helixscreen` | `lmd.d/30-helixscreen.sh` bind-mounts HelixScreen over `/usr/bin/gui` | Open-source touchscreen UI, so it can be modified to show 8 tools |
| `firmware-extended/40-feature-upgrade-firmware/apps/firmware-imposter` | LD_PRELOAD shim on `lmd` and `unisrv` | Shows the closed binaries can be intercepted if needed |

**Answer: can overlays replace Klipper modules and configs?** Yes, fully.
- Python modules: `patches/home/lava/klipper/**.patch` (zero-fuzz), or `root/home/lava/klipper/klippy/...` for whole-file replacement or addition.
- Factory configs: `patches/home/lava/origin_printer_data/config/*.patch`.
- Runtime overrides: `extended/klipper/*.cfg`.
- **What overlays cannot reasonably change:**
  - the closed binaries `gui`, `unisrv`, `lmd`, other than by LD_PRELOAD tricks or replacing `gui` with HelixScreen;
  - the MCU firmware blobs, since the project passes them through unmodified.

---

## 5. Community discussion about more toolheads

- **Not completed in this session.** The GitHub issues search (`gh`), WebFetch of the issues page and `git log --grep` were all declined. The local clone is shallow (single commit), so it has no history.
- **No local evidence found.** The clone has no docs, issues or code that mention more than 4 toolheads, a second row, or 8 tools. The only multi-tool expansion work present is AFC-Lite, which maps lanes onto the existing 4 extruders.
- **Pointers for a follow-up:**
  - The README states the project does not accept feature requests.
  - The community lives on the Snapmaker Discord `#u1-printer` channel.
  - Also check the GitHub issues and discussions for "toolhead", "extruder4", "second row", "8 tools" and "max_physical_extruder_num".

---

## 6. Recommendation: deploying an 8-tool experiment

### Phase 0: no hardware, no rebuild (days)
1. Install the extended firmware and enable SSH. Optionally create `/oem/.debug` so changes to `/` persist.
2. Extend the simulator for the new tools:
   - copy `S59toolhead-sim` to a modified version with `TOOLHEADS="... 5:e4 6:e5 7:e6 8:e7"`;
   - point new `[mcu e4..e7] serial: /tmp/klipper_host_e4..7` entries at the simulated MCUs.

   All of this goes in `/oem/printer_data/config/extended/klipper/8tool.cfg`.
3. In the same file, add `[extruder4..7]` and `[park_detector extruder4..7]` by cloning `[extruder1]`, with placeholder second-row `xy_park_position` values.
4. Override `[printer] max_physical_extruder_num: 8`.
5. Run Klipper and record every failure. Expected failures:
   - `toolhead.py:696` index logic;
   - the extruder-name parsing in `kinematics/extruder.py`;
   - `print_stats`, `pause_resume`, `exclude_object`;
   - `filament_feed` and `fm175xx` channel maps;
   - the `_FILAMENT_FEED_VARIABLE` lists;
   - park-detector ADC pins.

   Alternative test environments: `scripts/dev/qemu.sh` (with the `qemu` mod) or `scripts/dev/run-klipper.sh`, so nothing is risked on the printer.

### Phase 1: personal mod overlay (weeks)
1. Create `overlays/mods/<user>/` with numbered subdirectories:
   - `NN-8tool-klipper/patches/home/lava/klipper/...`: patches to `toolhead.py`, `kinematics/extruder.py`, `extras/print_stats.py`, `extras/filament_feed.py`, `extras/park_detector.py` (or similar), plus the feed and RFID channel maps. Use the dos2unix pre-script for any CRLF file.
   - `NN-8tool-config/patches/home/lava/origin_printer_data/config/printer.cfg.patch`, or keep the 8-tool sections purely in `root/.../extended/klipper/` include files.
   - `NN-8tool-sim/root/etc/init.d/S59toolhead-sim`: a replacement with 8 entries, for bench testing.
2. Build: `./dev.sh make build PROFILE=extended-<user>`.
3. Iterate with `scripts/dev/upgrade-rootfs.sh`. It copies `root/` only, so either ship modified Python files as whole-file copies during iteration or apply patches by hand.
4. Commit to a full image with `scripts/dev/upgrade-firmware.sh` (`systemUpgrade.sh upgrade soc`). This writes the inactive slot, so the previous slot stays as a fallback.
5. Use the web UI (Fluidd/Mainsail) and/or a modified HelixScreen for 8-tool control. Expect the stock touchscreen GUI to be unusable or misleading for T4-T7.

### Phase 2: real hardware
- **Connecting toolheads 5-8:**
  - Connect the extra toolhead boards over a USB hub and bind them by `by-path` (or by `by-id` serial, which is more robust with a cascaded hub).
  - Toolhead boards must run Snapmaker's toolhead Klipper firmware (`at32f415.bin`, from the same Klipper version as the host).
  - Alternatively use CAN via a USB-CAN adapter, following the AFC mod pattern.
- **Park detection:**
  - Move park detection for T4-T7 to toolhead-local pins, or add an extra MCU (e.g. a small Klipper board) for the additional ADC park sensors.
  - Keep `MAIN_MCU_POWER/HEAD_MCU_POWER` behaviour in mind: new boards need their own power sequencing.

### Recovery plan (keep at hand)
- In order of escalation:
  1. Remove `extended/klipper/8tool.cfg` and restart Klipper.
  2. Use the `extended-recover.txt` / `full-recover.txt` USB files.
  3. Use firmware-config "Switch to Backup Firmware" or `updateEngine --misc=other --reboot`.
  4. Reflash a stock `.bin` via Local Update.
- Do not run `systemUpgrade.sh upgrade all` with a modified image unless you intend to reflash the MCUs.

### Risks
- **Closed-source GUI and `unisrv`.**
  - They likely hardcode 4 tools. They may misbehave, crash or reject state with 8 extruders, including cloud and print-job handling and the flow calibration in `flow_calc_server`.
  - Mitigation: use HelixScreen and the web UI, and disable cloud.
- **Klipper fork divergence.**
  - Snapmaker's Klipper extras are not upstream. Zero-fuzz patches break on every stock firmware bump (base currently 2.0.0.205), and the AFC mod shows this maintenance cost.
- **Main-MCU I/O is fixed.** Park detectors (4 ADC), feeders and RFID are wired to the main board, so a second row needs new hardware paths for these functions.
- **USB.** Hub port count, bandwidth and power budget for 8 toolhead MCUs plus their fans and steppers. Path-based naming is fragile behind extra hubs.
- **Safety.**
  - Simulated MCUs report fake temperatures (`pins.conf` values). Never combine simulated heater definitions with real heaters.
  - Thermal-runaway protection on real T4-T7 must be validated individually.
- **Mechanics and travel.** Docks currently sit at Y 332.2 of a 335 mm limit. Any second row changes the kinematic limits, collision envelope and grab-direction logic (`extruder_grab_dir`).
- **Data persistence.** Changes made under `/oem/.debug` are wiped by firmware upgrades. Keep everything in the mod overlay and in `extended/klipper/*.cfg`.
- **Slicer side.** Slicers expect `T0..T7` and `SET_PRINT_EXTRUDER_MAP` semantics. With `max_logical_extruder_num: 32`, logical indices 8+ must still map correctly.

---

## Open questions

1. **Community work on more than 4 toolheads.** Is there any existing discussion or prototype (GitHub issues, Snapmaker Discord `#u1-printer`, Reddit)? Not checked, because network lookups were declined.
2. **Toolhead MCU chip.** Is the toolhead MCU really AT32F415, as the board config and `at32f415.bin` suggest? Why is the simulator named `klipper-dummy-at32f403a`? And can the stock toolhead firmware be reused unchanged for boards 5-8, given it has no per-board identity because binding is by USB path?
3. **USB topology.** How many downstream ports does the internal hub have (ports 1.1-1.4 are used)? Is there a spare, and what is the 5 V budget?
4. **GUI and `unisrv` with more than 4 extruders.** How do they behave when Klipper reports 8 extruders: crash, ignore the extra tools, or corrupt state? This needs an experiment with simulated e4-e7.
5. **Code locations needing patches.** Exactly which Snapmaker extras index arrays by physical extruder count? Candidates are `toolhead.py:696`, `print_stats.py`, `pause_resume.py`, `exclude_object.py`, `filament_feed.py`, the park detector module and the `kinematics/extruder.py` name parser. A full grep for `max_physical_extruder_num` and literal `4` and `range(4)` in `refs/u1-klipper/klippy` is the next step (the Klipper toolchange report may cover this).
6. **Spare ADC pins.** Does the main MCU have spare analog pins for 4 more park detectors, or must park sensing move to the toolhead or an extra MCU?
7. **Toolhead firmware updates.** Does `systemUpgrade.sh upgrade all` flash all connected toolhead MCUs by enumerating USB devices? If so, will it try to flash boards 5-8, and will it handle them correctly?
8. **CAN as a transport.** Is CAN viable for toolhead MCUs? The onboard `can0` rear connector is reportedly not working in the community, and USB-CAN on `can1` is proven only for AFC units.
