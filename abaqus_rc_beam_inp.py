"""
Abaqus 3D 비선형 RC 보 모델 생성기 (.inp)
-----------------------------------------
rc-capacity.html 계산기와 같은 입력으로 3차원 솔리드 콘크리트(C3D8R) + 매입 철근(T3D2) 모델을 만들어
Abaqus 입력 파일 rc_beam.inp 를 씁니다. 콘크리트는 CDP(Concrete Damaged Plasticity), 철근은 이선형 소성.

실행:        python3 abaqus_rc_beam_inp.py          → out/rc_beam.inp
Abaqus 해석:  abaqus job=rc_beam input=out/rc_beam.inp cpus=4 interactive
결과 추출:    abaqus python abaqus_extract_pd.py rc_beam.odb   → rc_beam_pd.csv (하중–처짐)

좌표계: x = 경간 방향 (0 ~ L), y = 높이 (0 = 하연, h = 상연), z = 폭 (0 = 중심)
"""
import os, math

# ───────────────────────── 입력 (mm, N/mm²) ─────────────────────────
P = dict(
    b=300, h=500, d=440, bf=800, hf=120,          # 단면. 직사각형이면 bf = b 또는 hf = 0
    fck=30, fy=345, Es=200000,                   # 재료 특성값
    As_a=387.1, As_n=6, Asc_a=198.6, Asc_n=2, dc=40,   # 주철근: 공칭단면적 × 본수
    Aw_a=71.33, s=200, fwy=295, cover=40,        # 스터럽 (s = 0 이면 없음)
    L=6000, load_type="4point", a=2000,          # 경간, 재하 방식, 재하점 위치
    target_disp=60.0,                            # 재하점 강제변위 (mm)
    es=50,                                       # 요소 크기 (mm). 작을수록 정확하지만 느려요
    viscosity=0.0005,                            # CDP 점성 계수 (수렴 보조). 0.0001~0.001
)
# ──────────────────────────────────────────────────────────────────────


def ec_jsce(fck):
    tb = [(18, 22), (24, 25), (30, 28), (40, 31), (50, 33), (60, 35), (70, 37), (80, 38)]
    if fck <= 18: return 22e3
    if fck >= 80: return 38e3
    for (a, ea), (c, ec) in zip(tb, tb[1:]):
        if fck <= c: return (ea + (ec - ea) * (fck - a) / (c - a)) * 1e3


def cdp_tables(fck, Ec):
    """CDP 재료 표. 압축: 포물선(ε0 = 2f'c/Ec)까지 상승 후 0.0035에서 0.2f'c, 0.01까지 유지.
    인장: 파괴에너지 Gf (MC2010: 73·fcm^0.18 N/m) 기반 선형 연화. 첫 행 비탄성변형률은 0이어야 해요."""
    fc = fck
    e0 = 2 * fc / Ec
    comp = []
    for e in [0.4 * e0] + [e0 * k / 10 for k in range(5, 11)] + [e0 + (0.0035 - e0) * k / 5 for k in range(1, 6)] + [0.006, 0.01]:
        if e <= e0:
            sig = fc * (2 * e / e0 - (e / e0) ** 2)
        elif e <= 0.0035:
            sig = fc - (fc - 0.2 * fc) * (e - e0) / (0.0035 - e0)
        else:
            sig = 0.2 * fc
        comp.append((sig, e - sig / Ec))
    # 첫 행: 탄성한계 0.4 f'c 에서 비탄성변형률 0
    comp[0] = (0.4 * fc, 0.0)
    comp = [(s, max(0.0, ein)) for s, ein in comp]
    # 비탄성변형률이 단조증가하도록 정리
    out, last = [], -1
    for s, ein in comp:
        if ein > last: out.append((s, ein)); last = ein
    ft = 0.23 * fck ** (2 / 3)
    Gf = 73 * (fck + 8) ** 0.18 / 1000          # N/mm
    wc = 2 * Gf / ft                            # 응력이 0이 되는 균열폭 (선형 연화)
    return out, ft, Gf, wc


def build(p):
    b, h, L, es = p["b"], p["h"], p["L"], p["es"]
    bf = max(p["bf"], b) if p["hf"] > 0 else b
    hf = min(p["hf"], h) if p["hf"] > 0 else 0
    nx, ny, nz = max(1, round(L / es)), max(1, round(h / es)), max(2, round(bf / es))
    nz += nz % 2                                    # 짝수로 → z = 0 에 절점
    xs = [L * i / nx for i in range(nx + 1)]
    ys = [h * j / ny for j in range(ny + 1)]
    zs = [-bf / 2 + bf * k / nz for k in range(nz + 1)]
    nid = lambda i, j, k: 1 + i + (nx + 1) * (j + (ny + 1) * k)
    in_T = lambda yc, zc: abs(zc) <= b / 2 + 1e-9 or yc >= h - hf - 1e-9    # 웨브 안 또는 플랜지 안
    elems, used = [], set()
    eid = 1
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                yc, zc = (ys[j] + ys[j + 1]) / 2, (zs[k] + zs[k + 1]) / 2
                if not in_T(yc, zc): continue
                n = [nid(i, j, k), nid(i + 1, j, k), nid(i + 1, j + 1, k), nid(i, j + 1, k),
                     nid(i, j, k + 1), nid(i + 1, j, k + 1), nid(i + 1, j + 1, k + 1), nid(i, j + 1, k + 1)]
                elems.append((eid, n)); used.update(n); eid += 1
    nodes = {nid(i, j, k): (xs[i], ys[j], zs[k]) for k in range(nz + 1) for j in range(ny + 1) for i in range(nx + 1) if nid(i, j, k) in used}

    # 철근 절점·요소 (콘크리트 절점과 독립, *EMBEDDED ELEMENT 로 결합)
    rn, re_, rid, reid = {}, [], 1_000_000, 1_000_000
    def bar_line(y, z, area_tag):
        nonlocal rid, reid
        ids = []
        for x in xs:
            rid += 1; rn[rid] = (x, y, z); ids.append(rid)
        for a_, b_ in zip(ids, ids[1:]):
            reid += 1; re_.append((reid, a_, b_, area_tag))
    def spread(n, half):   # n본을 웨브 폭 안에 균등 배치 (피복 고려)
        if n == 1: return [0.0]
        return [-half + 2 * half * i / (n - 1) for i in range(n)]
    zw = b / 2 - p["cover"] - 10
    for z in spread(p["As_n"], zw): bar_line(h - p["d"], z, "TENS")
    if p["Asc_n"] > 0:
        for z in spread(p["Asc_n"], zw): bar_line(h - p["dc"], z, "COMP")
    # 스터럽: 피복선을 따라 닫힌 사각 고리, 간격 s
    n_stir = 0
    if p["s"] > 0:
        c = p["cover"]
        corners = [(c, -zw), (h - c, -zw), (h - c, zw), (c, zw)]
        x = p["s"] / 2
        while x < L:
            ids = []
            for yy, zz in corners:
                rid += 1; rn[rid] = (x, yy, zz); ids.append(rid)
            for a_, b_ in zip(ids, ids[1:] + ids[:1]):
                reid += 1; re_.append((reid, a_, b_, "STIR"))
            n_stir += 1; x += p["s"]

    # 지점·재하 절점 (격자에 스냅)
    snap = lambda v, arr: min(arr, key=lambda t: abs(t - v))
    x_sup = (xs[0], xs[-1])
    x_load = [snap(v, xs) for v in ((p["a"], L - p["a"]) if p["load_type"] == "4point" else (L / 2,))]
    sel = lambda cond: [n for n, c in nodes.items() if cond(*c)]
    sets = {
        "SUP_L": sel(lambda x, y, z: x == x_sup[0] and y == 0 and abs(z) <= b / 2 + 1e-9),
        "SUP_R": sel(lambda x, y, z: x == x_sup[1] and y == 0 and abs(z) <= b / 2 + 1e-9),
        "LOAD": sel(lambda x, y, z: x in x_load and y == h),
        "MID_BOT": [min(sel(lambda x, y, z: y == 0), key=lambda n: abs(nodes[n][0] - L / 2) + abs(nodes[n][2]))],
    }
    return dict(nodes=nodes, elems=elems, rn=rn, re=re_, sets=sets, x_load=x_load, n_stir=n_stir, bf=bf, hf=hf, mesh=(nx, ny, nz))


def write_inp(p, m, path):
    Ec = ec_jsce(p["fck"])
    comp, ft, Gf, wc = cdp_tables(p["fck"], Ec)
    o = []
    w = o.append
    w(f"*HEADING\n RC beam 3D nonlinear (CDP) - generated by abaqus_rc_beam_inp.py\n L={p['L']} b={p['b']} h={p['h']} bf={m['bf']} hf={m['hf']} fck={p['fck']} mesh={m['mesh']}")
    w("*PREPRINT, ECHO=NO, MODEL=NO, HISTORY=NO")
    w("*NODE, NSET=N_CONC")
    for n, (x, y, z) in sorted(m["nodes"].items()): w(f"{n}, {x:.3f}, {y:.3f}, {z:.3f}")
    w("*ELEMENT, TYPE=C3D8R, ELSET=CONCRETE")
    for e, n in m["elems"]: w(f"{e}, " + ", ".join(map(str, n)))
    w("*NODE, NSET=N_REBAR")
    for n, (x, y, z) in sorted(m["rn"].items()): w(f"{n}, {x:.3f}, {y:.3f}, {z:.3f}")
    for tag in ("TENS", "COMP", "STIR"):
        els = [r for r in m["re"] if r[3] == tag]
        if not els: continue
        w(f"*ELEMENT, TYPE=T3D2, ELSET=BAR_{tag}")
        for e, a, b_, _ in els: w(f"{e}, {a}, {b_}")
    for name, ids in m["sets"].items():
        w(f"*NSET, NSET={name}")
        for i in range(0, len(ids), 16): w(", ".join(map(str, ids[i:i + 16])))
    # 단면
    w("*SECTION CONTROLS, NAME=HG, HOURGLASS=ENHANCED")
    w("*SOLID SECTION, ELSET=CONCRETE, MATERIAL=CONC, CONTROLS=HG\n1.0")
    w(f"*SOLID SECTION, ELSET=BAR_TENS, MATERIAL=STEEL\n{p['As_a']:.2f}")
    if p["Asc_n"] > 0: w(f"*SOLID SECTION, ELSET=BAR_COMP, MATERIAL=STEEL\n{p['Asc_a']:.2f}")
    if m["n_stir"]: w(f"*SOLID SECTION, ELSET=BAR_STIR, MATERIAL=STIRRUP\n{p['Aw_a']:.2f}")
    bars = ", ".join(t for t, ok in (("BAR_TENS", True), ("BAR_COMP", p["Asc_n"] > 0), ("BAR_STIR", m["n_stir"] > 0)) if ok)
    w(f"*EMBEDDED ELEMENT, HOST ELSET=CONCRETE\n{bars}")
    # 재료
    w("*MATERIAL, NAME=CONC")
    w(f"*DENSITY\n2.4E-9")
    w(f"*ELASTIC\n{Ec:.0f}, 0.2")
    w(f"*CONCRETE DAMAGED PLASTICITY\n36., 0.1, 1.16, 0.667, {p['viscosity']}")
    w("*CONCRETE COMPRESSION HARDENING")
    for s_, ein in comp: w(f"{s_:.4f}, {ein:.6f}")
    w(f"*CONCRETE TENSION STIFFENING, TYPE=GFI\n{ft:.4f}, {Gf:.5f}")
    w(f"*CONCRETE TENSION DAMAGE, TYPE=DISPLACEMENT\n0., 0.\n0.5, {0.25 * wc:.5f}\n0.9, {0.9 * wc:.5f}")
    w("*CONCRETE COMPRESSION DAMAGE")   # 상승 구간 0, 하강 구간 1 − σ/f'c (단조증가, 최대 0.9)
    peak = max(range(len(comp)), key=lambda i: comp[i][0]); d = 0.0
    for i, (s_, ein) in enumerate(comp):
        if i > peak: d = max(d, min(0.9, 1 - s_ / p["fck"]))
        w(f"{d:.4f}, {ein:.6f}")
    for name, fy in (("STEEL", p["fy"]), ("STIRRUP", p["fwy"])):
        w(f"*MATERIAL, NAME={name}\n*DENSITY\n7.85E-9\n*ELASTIC\n{p['Es']:.0f}, 0.3\n*PLASTIC\n{fy:.1f}, 0.\n{fy * 1.1:.1f}, 0.05")
    # 경계조건·해석
    w("*BOUNDARY\nSUP_L, 1, 3\nSUP_R, 2, 3")
    w("*STEP, NAME=LOAD, NLGEOM=NO, INC=2000\n*STATIC\n0.005, 1., 1E-7, 0.02")
    w("*CONTROLS, PARAMETERS=TIME INCREMENTATION\n, , , , , , , 30, , , \n*CONTROLS, PARAMETERS=FIELD, FIELD=DISPLACEMENT\n0.01, 0.05")
    w(f"*BOUNDARY\nLOAD, 2, 2, {-p['target_disp']:.2f}")
    w("*OUTPUT, FIELD, FREQUENCY=5\n*NODE OUTPUT\nU, RF\n*ELEMENT OUTPUT, ELSET=CONCRETE\nS, E, PE, PEEQ, PEEQT, DAMAGET, DAMAGEC, SDEG\n*ELEMENT OUTPUT, ELSET=BAR_TENS\nS, PE")
    w("*OUTPUT, HISTORY, FREQUENCY=1\n*NODE OUTPUT, NSET=LOAD\nRF2, U2\n*NODE OUTPUT, NSET=MID_BOT\nU2\n*NODE OUTPUT, NSET=SUP_L\nRF2\n*NODE OUTPUT, NSET=SUP_R\nRF2")
    w("*END STEP")
    with open(path, "w") as fp: fp.write("\n".join(o) + "\n")
    return Ec, comp, ft, Gf, wc


def main():
    os.makedirs("out", exist_ok=True)
    m = build(P)
    Ec, comp, ft, Gf, wc = write_inp(P, m, "out/rc_beam.inp")
    nx, ny, nz = m["mesh"]
    print("=== Abaqus 입력 파일 out/rc_beam.inp ===")
    print(f"콘크리트 절점 {len(m['nodes'])}, C3D8R 요소 {len(m['elems'])} (격자 {nx}×{ny}×{nz}, 요소 {P['es']} mm)")
    print(f"철근 절점 {len(m['rn'])}, T3D2 요소 {len(m['re'])} (주근 {P['As_n']}+{P['Asc_n']}본, 스터럽 {m['n_stir']}조)")
    print(f"재하점 x = {m['x_load']} (격자에 스냅), 재하 절점 {len(m['sets']['LOAD'])}개, 지점 절점 {len(m['sets']['SUP_L'])}+{len(m['sets']['SUP_R'])}개")
    print(f"CDP: Ec = {Ec:.0f}, ft = {ft:.2f} N/mm², Gf = {Gf:.4f} N/mm, 균열폭 wc = {wc:.4f} mm, 압축표 {len(comp)}행")
    print("해석: abaqus job=rc_beam input=out/rc_beam.inp cpus=4 interactive")


if __name__ == "__main__":
    main()
