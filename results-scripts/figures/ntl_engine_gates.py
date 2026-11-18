"""Estimation engine for the nightlights specification grid. Two-way FE, cluster and Conley."""
import numpy as np, pandas as pd
from scipy import stats


def absorb(M, keys, maxit=400, tol=1e-11):
    M = np.asarray(M, float).copy(); pre = []
    for k in keys:
        c_, u_ = pd.factorize(pd.Series(k))
        pre.append((c_, len(u_), np.bincount(c_, minlength=len(u_)).astype(float)))
    for _ in range(maxit):
        chg = 0.0
        for c_, n, cnt in pre:
            num = np.zeros((n, M.shape[1])); np.add.at(num, c_, M)
            d = (num / np.maximum(cnt, 1e-12)[:, None])[c_]
            chg = max(chg, float(np.abs(d).max())); M -= d
        if chg < tol: break
    return M


def ols(yv, Xm, sid, P=None, cutoff=25.0):
    XtX = Xm.T @ Xm
    if np.linalg.matrix_rank(XtX) < XtX.shape[0]:
        return None
    b = np.linalg.solve(XtX, Xm.T @ yv); e = yv - Xm @ b; inv = np.linalg.inv(XtX)
    G = pd.factorize(pd.Series(sid))[0]; ng = G.max() + 1
    S = np.zeros((ng, Xm.shape[1])); np.add.at(S, G, Xm * e[:, None])
    V = inv @ (S.T @ S) @ inv * (ng / max(ng - 1.0, 1))
    se = np.sqrt(np.maximum(np.diag(V), 0))
    cse = None
    if P is not None and len(yv) <= 20000:
        d = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)) / 1000.0
        W = np.maximum(0.0, 1.0 - d / cutoff); Xe = Xm * e[:, None]
        cse = np.sqrt(np.maximum(np.diag(inv @ (Xe.T @ W @ Xe) @ inv), 0))
    return b, se, cse, ng


def did(df, ycol, treatcol, unitcol, timecol, sidcol, t0, xy=None):
    """two-way FE difference-in-differences; treat may be binary or continuous"""
    s = df[df[ycol].notna() & df[treatcol].notna()].copy()
    if s.empty or s[timecol].nunique() < 3: return None
    s["post"] = (s[timecol] >= t0).astype(float)
    if s.post.nunique() < 2: return None
    M = np.column_stack([s[ycol].to_numpy(float), (s[treatcol] * s.post).to_numpy(float)])
    R = absorb(M, [s[unitcol].to_numpy(), s[timecol].to_numpy()])
    P = np.array([xy[i] for i in s[sidcol]]) if xy is not None else None
    r = ols(R[:, 0], R[:, 1:], s[sidcol].to_numpy(), P)
    if r is None: return None
    b, se, cse, ng = r
    out = dict(b=float(b[0]), se=float(se[0]),
               p=float(2 * (1 - stats.norm.cdf(abs(b[0] / se[0])))) if se[0] > 0 else np.nan,
               n=len(s), units=s[unitcol].nunique(), sectors=ng)
    if cse is not None and cse[0] > 0:
        out["se_conley"] = float(cse[0])
        out["p_conley"] = float(2 * (1 - stats.norm.cdf(abs(b[0] / cse[0]))))
    return out


def rings_did(df, ycol, ringcol, unitcol, timecol, sidcol, t0, ref="20+",
              order=("0-2", "2-5", "5-10", "10-20", "20+")):
    """one coefficient per distance band, each against the omitted far band"""
    s = df[df[ycol].notna() & df[ringcol].notna()].copy()
    if s.empty: return None
    s["post"] = (s[timecol] >= t0).astype(float)
    if s.post.nunique() < 2: return None
    use = [r_ for r_ in order if r_ != ref and (s[ringcol] == r_).any()]
    X = [((s[ringcol] == r_).astype(float) * s.post).to_numpy() for r_ in use]
    R = absorb(np.column_stack([s[ycol].to_numpy(float)] + X),
               [s[unitcol].to_numpy(), s[timecol].to_numpy()])
    r = ols(R[:, 0], R[:, 1:], s[sidcol].to_numpy())
    if r is None: return None
    b, se, _, ng = r
    return pd.DataFrame({"band": use, "b": b, "se": se,
                         "p": 2 * (1 - stats.norm.cdf(np.abs(b / np.maximum(se, 1e-12)))),
                         "n": len(s), "sectors": ng})


def event(df, ycol, treatcol, unitcol, timecol, sidcol, ref):
    s = df[df[ycol].notna() & df[treatcol].notna()].copy()
    per = sorted(s[timecol].unique())
    use = [p for p in per if p != ref]
    X = [(s[treatcol] * (s[timecol] == p)).to_numpy(float) for p in use]
    R = absorb(np.column_stack([s[ycol].to_numpy(float)] + X),
               [s[unitcol].to_numpy(), s[timecol].to_numpy()])
    r = ols(R[:, 0], R[:, 1:], s[sidcol].to_numpy())
    if r is None: return None
    b, se, _, _ = r
    ev = pd.DataFrame({"period": use, "b": b, "se": se})
    return pd.concat([ev, pd.DataFrame({"period": [ref], "b": [0.0], "se": [0.0]})]).sort_values("period")
