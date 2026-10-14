# 06 — Official wiki check and the stacked dock row idea

Date: 2026-10-15.

The official wiki (wiki.snapmaker.com) is rendered with JavaScript, and guests cannot read page sources through its API. `tools/wiki_fetch.py` therefore pulls the rendered HTML and saves each page as text. The 29 relevant U1 pages are in [wiki/](wiki/), including specs, dock and toolhead maintenance, hub, PSU, top cover and filament path. Only the XY belt guide was blocked (403).

## 1. What the wiki confirms or corrects

| Topic | Before | Wiki | Source |
|---|---|---|---|
| Latch slide | "~10 mm X slide" | **8.5 mm**. The calibration check is `G1 X-8.5` for head 1 and `X8.5` for heads 2–4 (= `horizontal_move_x 10 − retract_x_dist 1.5`) | [pick & park](wiki/u1_how_to_adjust_the_pick_and_park_coordinates.md) |
| Dock coordinates | Y = 332.2 from `printer.cfg` | Default only. Calibrated per machine and stored in `/persistent/extruder_config.json` | same, [main board](wiki/main_control_board_replacement_guide.md) |
| Dock hardware | — | The docking bracket is on the **rear beam** (4 screws). Each head has a parking tool on it (left one for head 1, right type for 2–4; 2 screws each). Below it are the nozzle wipers and a purge tray. Each head has a Hall sensor board on the bracket | [docking bracket](wiki/toolhead_docking_bracket_replacement_guide.md), [parking tool](wiki/parking_bracket_replacement_guide.md), [wiper](wiki/nozzle_wiper_replacement_guide.md) |
| Head ↔ swapper | — | Pull pin + pull bolt latch, 2 side locating pins, steel pin / steel ball coupling, pogo pins (3-pin, rated 250 000 swaps). The **part cooling fan is on the swapper**, not the head | [toolhead replacement](wiki/toolhead_replacement_guide.md), [pogo pins](wiki/pogopin_contact_anomaly.md), [maintenance](wiki/core_components_maintenance_guide.md) |
| Umbilicals | Unknown | Every head is permanently connected. A USB-C cable runs from the head top to the **HUB board under the top panel**, beside a **6/4.6 mm PTFE tube, 650 mm long**, from the head to a quick connector on the top panel | [toolhead cable](wiki/toolhead_cable_replacement_guide.md), [filament tube](wiki/filament_tube_replacement_guide.md) |
| Dock sensors | 4 ADC pins on the main MCU | The Hall boards are **cabled to the HUB board**, which links to the main board. They may still end on those ADC pins, but they pass through the hub | [hub board](wiki/hub_board_replacement_guide.md) |
| Expansion | Unknown | The main board has **"USB Expansion"** and **"CAN Board Expansion"** connectors | [main board](wiki/main_control_board_replacement_guide.md) |
| Power | Unknown | Max input is 1150 W at 220–240 V and 400 W at 100–120 V. The heated bed is **AC**, through its own control board, so the DC PSU only feeds hotends, motors and electronics. Three idle heads draw 10–30 W. The DC rating is still not stated | [FAQ](wiki/u1.md), [PSU](wiki/power_supply_replacement_guide.md) |
| Size | — | **Frame body 448 mm high**, 420 mm wide (584 with spool holders), 499 mm deep. **730 mm** overall includes the umbilical loops, about 280 mm above the top panel. The Top Cover makes it 584 × 510 × **751** mm | [FAQ](wiki/u1.md), `https://wiki.snapmaker.com/faq/dimensions.jpg` |
| Not in the wiki | — | Toolhead dimensions and weight, hub chip, toolhead MCU (AT32F415 vs F403A), DC PSU wattage | — |

## 2. Second row stacked on top of the original, swapped by a lift

### Why it is attractive
- **Same XY pick/park positions for T4–T7 as for T0–T3.** There are no mirrored moves, no travel extension and no frame extension. The firmware only needs one extra step before a pick: "make sure the right tier is at the working level".
- The swapper, the 8.5 mm latch and the pogo interface stay stock. The dock zone already has the full 4-slot width.
- The space above the dock row is outside the moving gantry's reach, so there is nothing to collide with apart from the umbilicals.

### The geometric catch
The gantry and swapper work in one fixed Z plane, so a head can only be picked at that level. An upper head can only come down if the lower head in the same slot gets out of the way. With a vertical rack, that means **one tier is always above or below the working level**.

| Rack state | Working level | Other tier |
|---|---|---|
| Bank A active | T0–T3 | T4–T7 one tier pitch **above** (sticks out above the frame top) |
| Bank B active | T4–T7 | T0–T3 one tier pitch **below** (in the rear zone under the docks) |

Numbers from the scan and the wiki (machine Z = nozzle plane = 0):

| Item | Value | Source |
|---|---|---|
| Frame top above nozzle plane | ≈ 110 mm | scan |
| Head + swapper top above nozzle | ≈ 126 mm | scan (active head) |
| Head-top connector for cable and tube | ≈ 15–25 mm (estimate) | wiki photos |
| **Tier pitch** (head + connector + wiper + clearance) | **≈ 150–170 mm** (to be measured) | estimate |
| Upper tier stored: head tops above the frame top | ≈ 150 + 126 − 110 ≈ **170 mm** | derived |
| Current umbilical loops above the frame top | ≈ 280 mm | wiki drawing |
| Lower tier dropped: nozzles below the working plane | ≈ **150–170 mm**, over ≈ 300 × 80 mm (X × Y) | derived |

So the concept needs both of these:

1. **About 170 mm of headroom above the frame top** behind the gantry. That height is available, because the umbilical loops already reach 280 mm, but **the Top Cover can't be used** and a taller hood is needed for enclosure printing.
2. **About 150–170 mm of free height below the dock row** across the full dock width. **The scan can't answer this**: it stops at the wipers and purge tray, about 10 mm above the nozzle plane. In the scan the dock positions show the bare bracket and wipers, so no heads were parked when it was taken.

If the space below is not available, the lower tier needs another way out:
- **Tilt back:** tier A swings up and backwards over the rear beam.
- **Lift and slide back:** a 2-axis rack.

Both are clearly more complex.

### Issues to solve
- **Wipers and purge tray.** These sit below the parked nozzles on the bracket. Each tier needs its own wipers moving with it, and the purge tray must move lower or become part of the rack. Otherwise the lower tier hits them on the way down.
- **Umbilical routing.** Tier A's cable and tube leave the top of each head straight upwards, exactly where tier B heads sit.
  - Route them **behind** tier B. That needs about 10–15 mm of depth between the head backs and the rear wall; measure it.
  - The 10 mm gaps between heads are too narrow.
  - Tier B gets its own exit points on or above the top panel.
  - The 650 mm tube with its loop has enough slack for the 150–170 mm tier move. The same loop already lets a picked head reach the front of the bed.
- **Repeatability.** The latch relies on the side pin entering the parking-tool slot, and Y calibration matters to about 1 mm. A motor alone is not enough: the rack should seat on **hard stops / kinematic seats** at both positions, with the motor only lifting. A self-locking lead screw keeps the rack in place when power is off.
- **Safety interlock.** The rack may only move when the swapper is outside the dock zone, with no head half-latched. Implement it in the toolchange macro, plus a rack-position sensor.
- **Load.** The rack holds 8 heads (weight not published; weigh one). A lead screw or belt with counterweight, guided on 2 linear rails fixed to the rear wall or rear beam.
- **Electronics.**
  - Second set of 4 Hall sensors.
  - A second hub, or the planned RP2040 board, for T4–T7 USB and power, the dock sensors and the rack stepper with endstop. The main board's USB/CAN expansion connectors are candidates for the link.
- **Print time.** A change between banks adds park → rack move (≈ 3–5 s) → pick. Colours used together in a layer should be put in the same bank.

### Variants
| Variant | Actuators | Pros | Cons |
|---|---|---|---|
| **Whole-rack elevator** (bank A / bank B) | 1 | Simplest mechanics and firmware | A change across banks moves all 4 heads |
| Per-slot elevators | 4 | Any 4 of the 8 at the working level | 4 × mechanics, interlocks, sensors; same space needed |

### Verdict
The stacked lift is the most firmware-friendly layout found so far: no new XY positions, and the printer keeps its full build volume. It **depends on one unmeasured number: the free height under the dock row**. If about 160 mm is free behind the bed down to that depth, across the full dock width, the whole-rack elevator is the recommended path.

### Measurements to take next
1. Free height below the purge tray in the rear zone (machine Y ≈ 290–370) across the full width, plus anything that moves there (Z belts/screws, bed carriage at its lowest).
2. Toolhead body height, nozzle tip to top of the cable/tube connector, with the head **off** the swapper. Also its depth and weight.
3. Gap between the back of a parked head and the rear wall, for tier A umbilical routing.
4. How the docking bracket mounts to the rear beam (screw pattern), since that would become the rack interface.
5. Optionally, a second scan from the front, with the bed fully lowered, looking into the rear zone.
