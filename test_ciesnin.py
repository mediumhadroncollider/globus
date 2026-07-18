import json
import numpy as np

d = np.load("world.npz")
punkty, lad = d["punkty"], d["lad"]
indptr, indices = d["indptr"], d["indices"]
zerw = set(map(tuple, np.stack([d["zerwane_a"], d["zerwane_b"]], axis=1).tolist()))

FI1, FI2 = np.radians(40), np.radians(68); LAM0 = np.radians(15)
_n = (np.sin(FI1)+np.sin(FI2))/2; _C = np.cos(FI1)**2 + 2*_n*np.sin(FI1)
_rho0 = np.sqrt(_C - 2*_n*np.sin(np.radians(52)))/_n
def proj(lon, lat):
    lam, fi = np.radians(lon), np.radians(lat)
    rho = np.sqrt(_C - 2*_n*np.sin(fi))/_n; th = _n*(lam-LAM0)
    return rho*np.sin(th), _rho0 - rho*np.cos(th)

rings = json.load(open("europa_wybrzeza.json"))
qx, qy = [], []
for r in rings:
    a = np.array(r); x, y = proj(a[:,0], a[:,1]); qx.append(x); qy.append(y)
qminx = min(x.min() for x in qx); qmaxx = max(x.max() for x in qx)
qmaxy = max(y.max() for y in qy)
meta = json.load(open("world_meta.json"))
allpx = np.concatenate([np.array(r) for r in meta["wybrzeze"]])
S = (allpx[:,0].max()-allpx[:,0].min())/(qmaxx-qminx)
pminx = allpx[:,0].min(); pminy = allpx[:,1].min()

def do_px(lon_arr, lat_arr):
    x, y = proj(lon_arr, lat_arr)
    return np.stack([(x-qminx)*S+pminx, (qmaxy-y)*S+pminy], axis=1)

CIESNINY = {
    "Mesyńska":    ((15.70,38.33),(15.40,37.85)),
    "Suur väin":   ((23.30,58.80),(23.50,58.35)),
    "Soela":       ((22.30,58.72),(22.95,58.69)),
    "Hiiumaa–ląd": ((23.05,59.15),(23.55,58.72)),
    "Öresund":     ((12.55,56.20),(12.95,55.30)),
    "Bosfor":      ((28.85,41.35),(29.25,40.85)),
    "Dardanele":   ((26.05,40.55),(26.80,39.90)),
}

ii = np.repeat(np.arange(len(lad)), np.diff(indptr)); jj = indices
m = (ii < jj) & lad[ii] & lad[jj]
A, B = ii[m], jj[m]
zywe = np.array([(a, b) not in zerw for a, b in zip(A.tolist(), B.tolist())])
A, B = A[zywe], B[zywe]
Ax, Ay = punkty[A,0], punkty[A,1]; Bx, By = punkty[B,0], punkty[B,1]

def orient(px, py, ax, ay, bx, by):
    return (bx-ax)*(py-ay) - (by-ay)*(px-ax)

ok = True
for nazwa, (p1, p2) in CIESNINY.items():
    s = do_px(np.array([p1[0], p2[0]]), np.array([p1[1], p2[1]]))
    s1x, s1y = s[0]; s2x, s2y = s[1]
    krzyzuje = (orient(Ax,Ay,s1x,s1y,s2x,s2y)*orient(Bx,By,s1x,s1y,s2x,s2y) < 0) & \
               (orient(s1x,s1y,Ax,Ay,Bx,By)*orient(s2x,s2y,Ax,Ay,Bx,By) < 0)
    n = int(krzyzuje.sum())
    if n: ok = False
    print(("OK " if n == 0 else "ZLE"), f"{nazwa}: sąsiedztw przecinających po zerwaniu = {n}")
print("WYNIK:", "wszystkie cieśniny szczelne" if ok else "nieszczelność!")
