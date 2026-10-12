"""
RC 보 파이버 단면 비선형 해석 (OpenSeesPy)
------------------------------------------
단면을 작은 조각(파이버)으로 나누고, 각 조각에 콘크리트(Concrete02)·철근(Steel02) 응력–변형률 곡선을 넣은 뒤
보를 변위제어로 눌러 가며 하중–처짐 곡선을 구합니다. 균열·철근 항복·종국 하중을 자동으로 찾아 표시합니다.

실행:  .venv/bin/python beam_fiber_opensees.py              (아래 P 딕셔너리 사용)
       .venv/bin/python beam_fiber_opensees.py Beam-01.json (계산기에서 저장한 케이스 JSON 사용)
출력:  out/beam_fiber.csv (단계별 처짐·하중·모멘트·변형률), out/beam_fiber.png (하중–처짐 곡선)

입력은 아래 P 딕셔너리만 고치면 됩니다 (rc-capacity.html 계산기와 같은 단위: mm, N/mm²).
"""
import os, csv, math
import numpy as np
import openseespy.opensees as ops

# ───────────────────────── 입력 ─────────────────────────
P = dict(
    # 단면 (mm). 직사각형이면 bf = b 또는 hf = 0
    b=300, h=500, d=440, bf=800, hf=120,
    # 재료 특성값 (N/mm²). 안전계수 없이 공칭값으로 해석
    fck=30, fy=345, Es=200000,
    # 철근: 공칭단면적 × 본수
    As=387.1 * 6, Asc=198.6 * 2, dc=40,
    # 보: 경간, 재하 방식, 재하점 위치 (4점: 양쪽 지점에서 a만큼 / 3점: 중앙)
    L=6000, load_type="4point", a=2000,
    # 해석 제어: 목표 중앙 처짐, 단계 수, 요소 수
    target_disp=150.0, steps=300, n_elem=20,
)
# ─────────────────────────────────────────────────────────


def ec_jsce(fck):
    """示方書 탄성계수 표 (kN/mm²) 선형 보간 → N/mm²"""
    tb = [(18, 22), (24, 25), (30, 28), (40, 31), (50, 33), (60, 35), (70, 37), (80, 38)]
    if fck <= 18: return 22e3
    if fck >= 80: return 38e3
    for (a, ea), (c, ec) in zip(tb, tb[1:]):
        if fck <= c:
            return (ea + (ec - ea) * (fck - a) / (c - a)) * 1e3


def nominal_moment(p):
    """계산기(rc-capacity.html)와 같은 등가응력블록 공칭 휨내력 Mu (kN·m), γ = 1.
    힘의 평형 Cc + Cs − T = 0 을 이분법으로 풀어요."""
    b, h, d, fck, fy, Es, As, Asc, dc = (p[k] for k in ("b", "h", "d", "fck", "fy", "Es", "As", "Asc", "dc"))
    bf = max(p["bf"], b) if p["hf"] > 0 else b
    hf = min(p["hf"], h) if p["hf"] > 0 else 0
    k1 = min(0.85, 1 - 0.003 * fck)
    ecu = min(0.0035, max(0.0025, (155 - fck) / 30000))
    beta = 0.52 + 80 * ecu
    clamp = lambda v: max(-fy, min(fy, v))

    def forces(x):
        a = min(beta * x, h)
        ov = max(0.0, min(a, hf))
        A1, A2 = b * a, (bf - b) * ov
        Cc = k1 * fck * (A1 + A2)
        yc = (A1 * a / 2 + A2 * ov / 2) / (A1 + A2) if A1 + A2 > 0 else 0
        es, esc = ecu * (d - x) / x, ecu * (x - dc) / x
        return a, Cc, yc, As * clamp(Es * es), Asc * clamp(Es * esc)

    lo, hi = 1e-6, h
    for _ in range(200):
        m = (lo + hi) / 2
        _, Cc, _, T, Cs = forces(m)
        if Cc + Cs - T > 0: hi = m
        else: lo = m
    x = (lo + hi) / 2
    _, Cc, yc, T, Cs = forces(x)
    return (T * d - Cc * yc - Cs * dc) / 1e6


def build_model(p):
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    b, h, L = p["b"], p["h"], p["L"]
    bf = max(p["bf"], b) if p["hf"] > 0 else b
    hf = min(p["hf"], h) if p["hf"] > 0 else 0
    Ec = ec_jsce(p["fck"])
    fc = p["fck"]

    # 재료. Concrete02: 압축 −, 인장 +. 인장강도 ftk = 0.23 f'ck^(2/3) (示方書)
    ft = 0.23 * fc ** (2 / 3)
    # 압축 정점 변형률 ε0 = 2f'c/Ec 로 두면 초기 접선계수가 示方書 Ec 와 같아져요. 종국 후 잔류강도 0.2f'c
    ec0 = 2 * fc / Ec
    ops.uniaxialMaterial("Concrete02", 1, -fc, -ec0, -0.2 * fc, -0.0035, 0.1, ft, Ec * 0.1)
    ops.uniaxialMaterial("Steel02", 2, p["fy"], p["Es"], 0.005, 18, 0.925, 0.15)   # 변형경화율 0.5%

    # 파이버 단면. y: 단면 높이 방향(위 +), 원점은 총단면 도심. z: 폭 방향
    Ac = b * h + (bf - b) * hf
    yg_top = (b * h * h / 2 + (bf - b) * hf * hf / 2) / Ac   # 상연에서 도심까지
    y_of = lambda depth_from_top: yg_top - depth_from_top          # 상연 기준 깊이 → 도심 기준 y
    ops.section("Fiber", 1)
    # 웨브: 높이 방향 40조각, 폭 방향 1조각
    ops.patch("rect", 1, 40, 1, y_of(h), -b / 2, y_of(0), b / 2)
    if hf > 0 and bf > b:   # 플랜지 돌출부 좌우
        for z0, z1 in ((-bf / 2, -b / 2), (b / 2, bf / 2)):
            ops.patch("rect", 1, 10, 1, y_of(hf), z0, y_of(0), z1)
    # 철근: 인장측 As @ d, 압축측 Asc @ dc. 폭 방향으로 3본·2본으로 나눠 배치 (합계가 같으면 결과 동일)
    ops.layer("straight", 2, 3, p["As"] / 3, y_of(p["d"]), -b / 2 + 50, y_of(p["d"]), b / 2 - 50)
    if p["Asc"] > 0:
        ops.layer("straight", 2, 2, p["Asc"] / 2, y_of(p["dc"]), -b / 2 + 50, y_of(p["dc"]), b / 2 - 50)

    # 절점·요소: 단순보, 재하점이 절점에 오도록 좌표 생성
    n = p["n_elem"]
    xs = sorted(set([i * L / n for i in range(n + 1)] + load_points(p) + [L / 2]))
    for i, x in enumerate(xs):
        ops.node(i + 1, x, 0.0)
    ops.fix(1, 1, 1, 0)                 # 좌단 핀
    ops.fix(len(xs), 0, 1, 0)           # 우단 롤러
    ops.geomTransf("Linear", 1)
    ops.beamIntegration("Lobatto", 1, 1, 5)
    for i in range(len(xs) - 1):
        ops.element("dispBeamColumn", i + 1, i + 1, i + 2, 1, 1)
    return xs, Ec, Ac, yg_top


def load_points(p):
    return [p["a"], p["L"] - p["a"]] if p["load_type"] == "4point" else [p["L"] / 2]


def run(p):
    xs, Ec, Ac, yg_top = build_model(p)
    node_of = lambda x: xs.index(x) + 1
    mid = node_of(p["L"] / 2)
    lp = [node_of(x) for x in load_points(p)]

    # 기준하중 (각 재하점에 −1), 변위제어로 중앙 처짐을 target까지
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    for nd in lp:
        ops.load(nd, 0.0, -1.0, 0.0)
    ops.system("BandGeneral"); ops.numberer("RCM"); ops.constraints("Plain")
    ops.test("NormDispIncr", 1e-6, 50, 0)
    ops.algorithm("Newton")
    dU = p["target_disp"] / p["steps"]
    ops.integrator("DisplacementControl", mid, 2, -dU)
    ops.analysis("Static")

    # 중앙 요소의 단면 응답을 읽기 위한 요소 번호 (중앙 절점 왼쪽 요소, 마지막 적분점)
    mid_elem = mid - 1
    rows = []
    for step in range(p["steps"]):
        ok = ops.analyze(1)
        if ok != 0:   # 수렴 실패 시 알고리즘 바꿔서 재시도
            for alg in ("ModifiedNewton", "KrylovNewton"):
                ops.algorithm(alg); ok = ops.analyze(1)
                if ok == 0: break
            ops.algorithm("Newton")
            if ok != 0:
                print(f"step {step}: 수렴 실패, 해석 종료"); break
        delta = -ops.nodeDisp(mid, 2)
        lam = ops.getLoadFactor(1)                 # 재하점 하나당 하중 (N)
        P_tot = lam * len(lp) / 1e3                # 총 하중 (kN)
        # 중앙 단면: 변형, 곡률, 상연·하연·철근 변형률
        eps0, kappa = ops.eleResponse(mid_elem, "section", 5, "deformation")
        eps_top = eps0 - kappa * yg_top
        eps_bot = eps0 + kappa * (p["h"] - yg_top)
        eps_s = eps0 + kappa * (p["d"] - yg_top)
        M_mid = ops.eleResponse(mid_elem, "section", 5, "force")[1] / 1e6
        rows.append((step + 1, delta, P_tot, abs(M_mid), eps_top, eps_bot, eps_s, kappa))
    return rows, Ec, Ac, yg_top, lp


def load_case(path):
    """계산기(rc-capacity.html)에서 저장한 케이스 JSON → P 딕셔너리. 직사각형·T형만 (박스·원형은 미지원)"""
    import json
    with open(path, encoding="utf-8") as fp:
        c = json.load(fp)
    i, g = c["inputs"], lambda k, d=0.0: float(i.get(k, d) or 0)
    sec = i.get("secType", "tee")
    if sec not in ("rect", "tee"):
        raise SystemExit(f"OpenSees 스크립트는 직사각형·T형만 지원해요 (케이스: {sec})")
    p = dict(P)
    p.update(b=g("b"), h=g("h"), d=g("d"), bf=g("bf") if sec == "tee" else g("b"), hf=g("hf") if sec == "tee" else 0.0,
             fck=g("fc"), fy=g("fy"), Es=g("Es"), As=g("As_a") * g("As_n") + g("As2_a") * g("As2_n"), Asc=g("Asc_a") * g("Asc_n"), dc=g("dc"),
             L=g("bmL", 6000), load_type="4point" if i.get("f3lt", "4") == "4" else "3point", a=g("f3a", 2000))
    if g("As2_n") > 0:   # 2단 배근은 합계를 가중평균 깊이에 둠
        p["d"] = (g("As_a") * g("As_n") * g("d") + g("As2_a") * g("As2_n") * g("d2")) / p["As"]
    print(f"케이스 불러옴: {path} ({i.get('caseName', '')}, {sec})")
    return p


def main():
    import sys
    p = load_case(sys.argv[1]) if len(sys.argv) > 1 else P
    os.makedirs("out", exist_ok=True)
    rows, Ec, Ac, yg_top, lp = run(p)
    arr = np.array(rows)
    delta, Pt, M, eps_top, eps_bot, eps_s = arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5], arr[:, 6]

    # 특성점: 균열(하연 변형률 > ft/Ec), 항복(철근 변형률 > fy/Es), 종국(최대 하중)
    ft = 0.23 * p["fck"] ** (2 / 3)
    i_cr = next((i for i, e in enumerate(eps_bot) if e > ft / Ec), None)
    i_y = next((i for i, e in enumerate(eps_s) if e > p["fy"] / p["Es"]), None)
    i_u = int(np.argmax(Pt))
    i_cu = next((i for i, e in enumerate(eps_top) if e < -0.0035), None)   # 압축연 ε'cu 도달 (示方書 종국 정의)

    # 대조값 1: 탄성 초기강성 (환산단면 EcIe 보 이론, 철근은 n = Es/Ec 배로 환산)
    bf = max(p["bf"], p["b"]) if p["hf"] > 0 else p["b"]; hf = min(p["hf"], p["h"]) if p["hf"] > 0 else 0
    n_ = p["Es"] / Ec
    Ac = p["b"] * p["h"] + (bf - p["b"]) * hf
    Ae = Ac + (n_ - 1) * (p["As"] + p["Asc"])
    ye = (Ac * yg_top + (n_ - 1) * (p["As"] * p["d"] + p["Asc"] * p["dc"])) / Ae   # 환산단면 도심 (상연 기준)
    Ig = (p["b"] * p["h"] ** 3 / 12 + p["b"] * p["h"] * (p["h"] / 2 - ye) ** 2 + (bf - p["b"]) * hf ** 3 / 12 + (bf - p["b"]) * hf * (hf / 2 - ye) ** 2
          + (n_ - 1) * (p["As"] * (p["d"] - ye) ** 2 + p["Asc"] * (p["dc"] - ye) ** 2))
    L, a = p["L"], p["a"]
    if p["load_type"] == "4point":
        k_theory = 1 / ((a * (3 * L * L - 4 * a * a)) / (24 * Ec * Ig) / 2) / 1e3   # kN/mm (총하중 P, 각 P/2)
    else:
        k_theory = 48 * Ec * Ig / L ** 3 / 1e3
    k_fem = Pt[0] / delta[0]
    # 대조값 2: 등가응력블록 공칭 Mu → 종국 하중
    Mu = nominal_moment(p)
    P_Mu = 2 * Mu / (a / 1e3) if p["load_type"] == "4point" else 4 * Mu / (L / 1e3)

    with open("out/beam_fiber.csv", "w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["step", "delta_mid_mm", "P_total_kN", "M_mid_kNm", "eps_top", "eps_bot", "eps_steel", "curvature_1/mm"])
        w.writerows(rows)

    print(f"=== RC 보 파이버 비선형 해석 ({p['load_type']}, L = {L} mm, a = {a} mm) ===")
    print(f"초기강성  FEM {k_fem:.3f} kN/mm  vs  환산단면 EcIe 보이론 {k_theory:.3f} kN/mm  (비 {k_fem / k_theory:.3f})")
    for name, i in (("균열", i_cr), ("철근 항복", i_y), ("ε'cu 도달", i_cu), ("최대 하중", i_u)):
        if i is not None:
            print(f"{name:8s}: P = {Pt[i]:7.1f} kN, δ = {delta[i]:6.2f} mm, M = {M[i]:6.1f} kN·m")
    i_ref, tagn = (i_cu, "ε'cu 도달") if i_cu is not None else (i_u, "최대 하중")
    if i_cu is None:
        print(f"※ 압축연이 ε'cu = 0.0035 에 이르지 않았어요 (마지막 상연 변형률 {eps_top[-1]:.5f}). target_disp 를 키우거나 최대 하중으로 비교해요.")
    print(f"종국 모멘트 FEM({tagn}) {M[i_ref]:.1f} kN·m  vs  등가응력블록 Mu {Mu:.1f} kN·m  (비 {M[i_ref] / Mu:.3f})")
    print(f"종국 하중   FEM({tagn}) {Pt[i_ref]:.1f} kN   vs  Mu 환산 {P_Mu:.1f} kN")
    print("파일: out/beam_fiber.csv, out/beam_fiber.png")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=130)
    ax.plot(delta, Pt, color="#1f5f8b", lw=2, label="OpenSees fiber (Concrete02 + Steel02)")
    ax.axhline(P_Mu, color="#a1452a", ls="--", lw=1, label=f"equivalent stress block Mu → P = {P_Mu:.0f} kN")
    ax.plot([0, Pt[0] / k_theory * 3], [0, Pt[0] * 3], color="#5d676c", ls=":", lw=1, label="elastic EcIg slope")
    for name, i, mk in (("crack", i_cr, "o"), ("yield", i_y, "s"), ("ε'cu", i_cu, "^"), ("max", i_u, "v")):
        if i is not None:
            ax.plot(delta[i], Pt[i], mk, color="#1d2326", ms=6)
            ax.annotate(f"{name}\n{Pt[i]:.0f} kN", (delta[i], Pt[i]), textcoords="offset points", xytext=(8, -18), fontsize=8)
    ax.set_xlabel("midspan deflection δ (mm)"); ax.set_ylabel("total load P (kN)")
    ax.set_xlim(0, delta.max() * 1.05); ax.set_ylim(0, max(Pt.max(), P_Mu) * 1.15)
    ax.grid(alpha=.3); ax.legend(fontsize=8, loc="lower right")
    ax.set_title(f"RC beam {p['load_type']}  L={L/1e3:.1f} m  b×h={p['b']}×{p['h']}  f'ck={p['fck']}  As={p['As']:.0f} mm²", fontsize=9)
    fig.tight_layout(); fig.savefig("out/beam_fiber.png")


if __name__ == "__main__":
    main()
