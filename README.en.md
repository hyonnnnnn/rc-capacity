# rc-capacity — RC section capacity calculator + beam analysis tools

[한국어](README.md) · [日本語](README.ja.md) · **English**

For the concrete laboratory, Yokohama National University. Based on the JSCE Standard Specifications for Concrete Structures (土木学会 コンクリート標準示方書).

| File | What | Run |
|---|---|---|
| `rc-capacity.html` | Section capacity calculator: rectangular, T, box and circular sections, two tension layers, flexural/shear/axial capacity, M-N interaction, design checks, M–φ curve, serviceability (crack width, deflection), shear design, beam-element FEM, educational 3D nonlinear FEM (displacement/load control, live σ–ε, orbit/pan), experiment CSV comparison, case JSON save/load, HTML report, Excel calculation sheet, Korean/Japanese/English | https://claude.ai/artifact/F4ZSJfPxLxHixJozJtna7R |
| `beam_fiber_opensees.py` | OpenSeesPy fibre-section nonlinear beam analysis → load–deflection curve (the standard tool for comparing with experiments) | `.venv/bin/python beam_fiber_opensees.py` |
| `abaqus_rc_beam_inp.py` | Generates an Abaqus input file: 3D solid concrete + CDP + embedded rebar | `python3 abaqus_rc_beam_inp.py` → `out/rc_beam.inp` |
| `abaqus_extract_pd.py` | Extracts a load–deflection CSV from an Abaqus .odb | `abaqus python abaqus_extract_pd.py rc_beam.odb` |

## Distributing to the lab (phone app / program)

Running `python3 build_dist.py` creates the distributable files in `dist/` (a single `index.html` of about 1.2 MB with ExcelJS inlined, plus the PWA manifest, service worker and icons). It uses the browser's standard download instead of the artifact-only save feature, so Excel, JSON, report and PNG saving work everywhere. `rc-capacity-app.zip` is `dist/` zipped.

Three ways:
1. **Send the file (simplest)**: send the single `dist/index.html` by chat, e-mail or USB. On a PC double-click it; on iPhone open it from the Files app in Safari; on Android open it in Chrome. Works without internet (only the fonts fall back to system fonts).
2. **Share a web address + home-screen app (recommended)**: it is published at **https://hyonnnnnn.github.io/rc-capacity/** (repository https://github.com/hyonnnnnn/rc-capacity, branch `gh-pages` = `dist/`). To update: `python3 build_dist.py` → `git add -A && git commit -m "..." && git push` → `git subtree push --prefix dist origin gh-pages`. Lab members open the address on their phone and tap "Add to Home Screen" (iPhone: Share → Add to Home Screen; Android: menu → Install app). It then launches from an app icon, and the service worker caches it so it opens offline. A new version is picked up automatically on the next launch after you rebuild and push.
3. **Claude artifact link**: share https://claude.ai/artifact/F4ZSJfPxLxHixJozJtna7R from its Share menu. Recipients need a Claude account.

### Desktop program (double-click to run)

`app.py` is a desktop program that shows `dist/index.html` in the system web view; bundled with PyInstaller it becomes an executable that needs no installation. The save buttons open the OS save dialog.
- macOS: `sh build_app.sh` → `release/RC내력계산기.app` (built and launched on this Mac, about 25 MB). It is unsigned, so if the first launch shows an "unidentified developer" warning, right-click → Open in Finder (or run `xattr -dr com.apple.quarantine "RC내력계산기.app"` in Terminal).
- Windows: install Python, then double-click `build_app.bat` → `release\RC내력계산기.exe` (single file; the WebView2 runtime ships with Windows 10/11). The Windows build must be made on Windows.
- To run during development: `.venv/bin/python app.py`. After editing the page, run `python3 build_dist.py` again.
- The index.html inside the bundle is a copy taken at build time, so rebuild and redistribute the program whenever the calculator changes.

Note: the 3D FEM runs on phones too, but use a PC for the "fine" element size. The service worker registers only over https (or localhost).

## Composite sections (material layers)

Add rectangular layers in the "Composite material layers" table to combine other materials with the RC section (centred; y0 from the top, thickness t, width w; where a layer overlaps concrete it replaces it). Available for rectangular, T and box sections.
- Materials: steel plate (fy, Es, elastic–perfectly plastic), UHPC (f′c, Ec; compression plateau at 0.85f′c, tension plateau at ft = 0.23f′c^(2/3) up to about 0.005), FRP sheet (Ef, ffu; tension only, zero after rupture).
- Capacity: with layers present, Mu (positive and negative) and the M–N interaction come from fibre-section analysis (design strengths, 11 axial-load levels). Shear, βn, serviceability, the beam-element analysis (EI from the transformed section) and the Excel formulas keep the RC equations (Excel records values only).
- 3D FEM: layer boundaries are inserted as mesh breakpoints and each element gets its material. Steel elements use von Mises secant plasticity, FRP elements rupture when the maximum principal stress exceeds ffu, and UHPC uses the damage model with its own f′c, Ec and ft. Bearing zones at supports and load points are one element size thick (including the concrete above a thin layer).
- Shear-connector slip (3D, "Steel-layer connection" option): the steel layer gets its own nodes and the coincident node pairs are joined by interface springs. In x the secant stiffness of the Ollgaard (1971) stud load–slip law Q = Pu(1 − e^(−0.709s))^0.4 (studs per row / pitch × tributary length, shared equally among the pairs in the column, update damping 0.6); y and z are rigid (no uplift). Output: max slip and Q row, live Q–s chart, Excel columns. A very large Pu reproduces full composite action (verified: 1e6 kN gives the same load at every step). 300×500 + bottom plate, 3-point L 3 m: Pu 90 kN, pitch 150, 2 per row → 300 kN at 7 mm (full composite 455), slip 0.8 mm; Pu 30, 300, 1 per row → slip 2.4 mm with Q approaching Pu.
- Verification (300×500 3-D22, γ = 1): bottom steel plate 300×12 (fy 325) → Mu 589 kN·m (plastic hand calculation ≈ 600); UHPC top 60 mm (f′c 150) → 175 (RC 166); FRP 300×1.2 (Ef 230 GPa, ffu 3000) → 421 (concrete crushing governs). 3D 3-point L 3 m up to 16 mm: plate 489 kN (still rising), FRP 315 (drops to 175 after rupture), UHPC 313 (RC 269).

## Once: Python environment

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## OpenSees fibre analysis (`beam_fiber_opensees.py`)

- Input: the `P` dictionary at the top of the file (same units as the calculator: mm, N/mm²). For a rectangle use `bf=b, hf=0`.
- Pass a file saved with "Save input JSON" in the calculator to run that case: `.venv/bin/python beam_fiber_opensees.py Beam-01.json` (rectangular and T only; two tension layers are merged at the weighted-average depth).
- The result `out/beam_fiber.csv` can be loaded directly into the calculator's "Experiment comparison" and overlaid with the 3D analysis and tests.
- Materials: Concrete02 (ε0 = 2f′c/Ec, ft = 0.23 f′ck^(2/3), residual 0.2f′c), Steel02 (0.5% strain hardening).
- Output: `out/beam_fiber.csv`, `out/beam_fiber.png`. The console prints the initial stiffness (compared with transformed-section beam theory), cracking, yield and ultimate loads, and the ratio to the stress-block Mu.
- Reference values: 300×500 3-D22 rectangle → peak 170.5 kN (Mu equivalent 165.8 kN, ratio 1.03). T 6-D22+2-D16 → 355.7 kN (ratio 1.06, ε′cu not reached).

## Abaqus model (`abaqus_rc_beam_inp.py`)

- C3D8R concrete (enhanced hourglass control) + T3D2 rebar (main bars and stirrups) with `*EMBEDDED ELEMENT`.
- CDP: dilation angle 36°, eccentricity 0.1, fb0/fc0 1.16, K 0.667, viscosity 0.0005. Compression parabola + descending branch, tension by GFI (Gf = 73 fcm^0.18 N/m), damage variables included.
- Supports: pin and roller node lines on the bottom face. Loading: prescribed displacement on top node lines. Output: history RF2 (load points), U2 (mid-span bottom).
- Run: `abaqus job=rc_beam input=out/rc_beam.inp cpus=4 interactive`
- If it does not converge: raise `viscosity` to 0.001, set `es` to 40, reduce `target_disp`.
- Abaqus could not be run in this folder, so only the input file structure was verified (node and element references, monotonic material tables, rebar positions).

## 3D nonlinear FEM (inside `rc-capacity.html`)

A simplified educational model that runs in the browser, meant for watching cracks spread and seeing the shape of the load–deflection curve. Use OpenSees or Abaqus for quantitative comparison.
- Tests (30×6×2 mesh): peak load / stress-block Mu equivalent = 3-point 1.27, 4-point 1.09, 6-D22+2-D16 0.99, 40×8×4 3-point 1.17.
- Main-bar bond option: perfect bond (default) / bond–slip (good or poor). In slip mode the main bars (tension and compression) become trusses with their own x degree of freedom per column, and each node is tied to the concrete by a secant spring (perimeter × tributary length) following the fib MC2010 pull-out bond–slip law (τ = τmax(s/s1)^0.4 → plateau → 0.4τmax at s3; good: τmax 2.5√f′c, s1 1.0, s2 2.0; poor: 1.25√f′c, 1.8, 3.6; s3 ≈ 0.5φ). Both ends are treated as hooked anchorages with stiff springs. Stirrups stay perfectly bonded. The bar DOFs are inserted right after the concrete nodes of their column (a permutation) to keep the bandwidth small. Output: max slip and bond stress row, live τ–s chart, slip and τ columns in the Excel step table.
  - 300×500 3-D22 3-point (125 mm, up to 20 mm): perfect bond 1.22 → good 1.19 (max slip 0.15 mm, τ 6.4), poor 1.29 (slip 0.42 mm, τ 3.8). The perfect-bond result is identical to before the slip code was added (permutation check).
- Crack model option: isotropic damage (default) / fixed crack / rotating crack. The rotating crack realigns the crack frame with the current principal strain directions every iteration (directional damage d1, d2 recorded by principal order) and sets the shear stiffness by coaxiality, G_ij = (σi − σj)/2(εi − εj) (the β input is ignored). The fixed crack locks the normal to the maximum principal stress direction at the moment ft is first exceeded, reduces only the normal stiffness by (1−d), and applies the shear retention factor β (default 0.2, approached as damage grows) on the crack plane; a second orthogonal crack forms when the in-plane tension exceeds ft again. Crack direction lines are drawn in the 3D view and the crack angle is shown when an element is clicked.
  - 300×500 3-D22 3-point (L 3 m): 125 mm elements → isotropic 1.22, fixed 1.35 (β 0.2) / 1.31 (β 0.01), rotating 1.29; 80 mm elements → isotropic 1.20, fixed 1.20, rotating 1.16. T 4-point (L 6 m, 200 mm): isotropic 1.17, fixed 1.17, rotating 1.15. On coarse meshes the fixed crack is stronger because cracked elements keep their vertical and shear stiffness (the isotropic model loses all of it).
