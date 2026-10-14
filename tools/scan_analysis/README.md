# Scan analysis: room for a second dock row

Analyses a 3D scan (binary STL) of the top section of a Snapmaker U1. It reports where a second row of toolhead docks could fit, checking each layout option from `research/00-summary.md` against the free space in the scan.

```
pip install numpy pillow
python tools/scan_analysis/analyze_scan.py research/3D/<scan>.stl [--out DIR] [--config my.json]
```

The output goes to `<stl dir>/analysis/` by default:

| File | Content |
|---|---|
| `report.md` | Verdict per option, vertical budget for a carousel, candidate slots, detected geometry, assumptions |
| `top_view.png` | Free / blocked / unseen map in machine coordinates, with travel, print area, docks and candidate slots |
| `sections_y.png` | Side sections (height vs Y) through each dock X |
| `sections_x.png` | Cross sections along the dock row, the front candidate row and the bed |
| `config_used.json` | Effective settings. Copy and edit it, then pass it with `--config` |

## How it works

1. **Height map.** Triangles are sampled into a 0.5 mm grid that keeps the highest Z per cell. The scan only sees surfaces from above.
2. **Detection.** The tool finds:
   - the frame top (outer rim);
   - the bed plate (the dominant low plane);
   - the gantry beam and the active head (the highest blob).
3. **Registration.** Machine = scan − offset.
   - X is fitted to the known dock X pattern (35 / 102.7 / 170.2 / 237.7).
   - Y assumes the bed centre is at machine Y 136. If the dock crosses in `top_view.png` don't sit on the docked heads, set `offset_x`/`offset_y`.
4. **Classification.** Each cell is classified as one of:
   - *free*: its top surface is below the nozzle plane minus `z_margin_mm`;
   - *blocked*: it holds structure, or lies in the bed footprint (the bed rises to the nozzle);
   - *unseen*: there is no data, or it is under moving parts.
5. **Options.** A dock slot is `head_width_mm` + 8.5 mm latch slide by `dock_depth_mm`. Each option reports the longest free stretch next to the needed size. Results are given *strict* (unseen counts as blocked) and *optimistic* (unseen counts as free).

## Knobs worth measuring

- `head_width_mm`, `dock_depth_mm`: the real dock footprint.
- `nozzle_z`: set this if the bed was not raised to the nozzle when scanning.
- `offset_y`: set this once one reference point is known in both the scan and machine coordinates.
