# -*- coding: utf-8 -*-
"""
Abaqus 결과(.odb)에서 하중-처짐 곡선을 뽑아 CSV로 저장. Abaqus 내장 파이썬(2.7)으로 실행해요.
    abaqus python abaqus_extract_pd.py rc_beam.odb
출력: rc_beam_pd.csv  (time, load_kN = 재하 절점 RF2 합의 절댓값, delta_mm = 중앙 하연 U2 절댓값)
"""
import sys, csv
from odbAccess import openOdb

path = sys.argv[1] if len(sys.argv) > 1 else "rc_beam.odb"
odb = openOdb(path, readOnly=True)
step = odb.steps[odb.steps.keys()[-1]]
inst = odb.rootAssembly.instances.keys()[0]
asm = odb.rootAssembly

def hist(set_name, var):
    """절점 세트의 히스토리 출력을 (시간, 합계) 로 합쳐요"""
    total = {}
    for key, region in step.historyRegions.items():
        if set_name not in key and not key.endswith(set_name): continue
        if var not in region.historyOutputs: continue
        for t, v in region.historyOutputs[var].data:
            total[t] = total.get(t, 0.0) + v
    return total

# 히스토리 출력은 절점마다 따로 저장되므로 절점 세트에 속한 절점 번호로 모아요
load_nodes = set(n.label for n in asm.nodeSets["LOAD"].nodes[0])
mid_nodes = set(n.label for n in asm.nodeSets["MID_BOT"].nodes[0])
rf, u = {}, {}
for key, region in step.historyRegions.items():
    if not key.startswith("Node "): continue
    label = int(key.split(".")[-1])
    if label in load_nodes and "RF2" in region.historyOutputs:
        for t, v in region.historyOutputs["RF2"].data: rf[t] = rf.get(t, 0.0) + v
    if label in mid_nodes and "U2" in region.historyOutputs:
        for t, v in region.historyOutputs["U2"].data: u[t] = v

out = path.replace(".odb", "_pd.csv")
with open(out, "wb") as fp:
    w = csv.writer(fp); w.writerow(["time", "load_kN", "delta_mm"])
    for t in sorted(rf):
        w.writerow([t, abs(rf[t]) / 1000.0, abs(u.get(t, 0.0))])
print("saved", out, len(rf), "rows; max load %.1f kN" % (max(abs(v) for v in rf.values()) / 1000.0))
odb.close()
