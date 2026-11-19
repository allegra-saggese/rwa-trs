"""OLS with absorbed fixed effects (Frisch-Waugh-Lovell), CR1 cluster SEs and the wild cluster
restricted bootstrap (WCR, Webb six-point weights by default, Rademacher optional; Cameron, Gelbach and Miller 2008; Roodman et al. 2019)."""
import numpy as np, pandas as pd

def _resid(A, D):
    if D is None or D.shape[1] == 0: return A
    b, *_ = np.linalg.lstsq(D, A, rcond=None); return A - D @ b

def fe_matrix(df, fes):
    """fes: list of column names; each becomes a full set of dummies (one dropped per FE beyond the first)."""
    mats = []
    for i, f in enumerate(fes):
        m = pd.get_dummies(df[f].astype(str), drop_first=i > 0, dtype=float).values
        mats.append(m)
    return np.hstack(mats) if mats else None

def cluster_se(X, u, g, k_extra):
    n, k = X.shape; G = np.unique(g)
    XtXi = np.linalg.pinv(X.T @ X); meat = np.zeros((k, k))
    for c in G:
        s = X[g == c].T @ u[g == c]; meat += np.outer(s, s)
    kk = k + k_extra; adj = len(G) / (len(G) - 1) * (n - 1) / (n - kk)
    return np.sqrt(np.diag(adj * XtXi @ meat @ XtXi))

def fe_ols(df, y, xs, fes, cluster, B=9999, seed=1, weights="webb"):
    d = df.dropna(subset=[y] + xs).reset_index(drop=True)
    D = fe_matrix(d, fes); kD = 0 if D is None else np.linalg.matrix_rank(D)
    Y = _resid(d[[y]].values.astype(float), D)[:, 0]; X = _resid(d[xs].values.astype(float), D)
    b = np.linalg.lstsq(X, Y, rcond=None)[0]; u = Y - X @ b; g = d[cluster].values
    se = cluster_se(X, u, g, kD); t = b / se
    rng = np.random.default_rng(seed); G = np.unique(g); gi = np.searchsorted(G, g)
    n, k = X.shape; adj = len(G) / (len(G) - 1) * (n - 1) / (n - k - kD)
    XtXi = np.linalg.pinv(X.T @ X)
    vals = [-1.0, 1.0] if weights == "rademacher" else [-np.sqrt(1.5), -1.0, -np.sqrt(.5), np.sqrt(.5), 1.0, np.sqrt(1.5)]
    W = rng.choice(vals, size=(len(G), B))
    agg = lambda v: np.bincount(gi, weights=v, minlength=len(G))
    p_wcb = []
    for j in range(len(xs)):
        Xr = np.delete(X, j, axis=1)
        br = np.linalg.lstsq(Xr, Y, rcond=None)[0] if Xr.shape[1] else np.zeros(0)
        fit_r = Xr @ br if Xr.shape[1] else np.zeros_like(Y); ur = Y - fit_r
        # cluster-level pieces: y* = fit_r + w_g ur  =>  X'y* = X'fit_r + C w,  C[:, g] = X_g' ur_g
        C = np.vstack([agg(X[:, m] * ur) for m in range(k)])           # k x G
        BB = XtXi @ (X.T @ fit_r)[:, None] + XtXi @ (C @ W)             # k x B
        h = X @ XtXi[j]
        a = agg(h * fit_r); b_ = agg(h * ur)                            # G
        M = np.vstack([agg(h * X[:, m]) for m in range(k)]).T           # G x k
        Sg = a[:, None] + b_[:, None] * W - M @ BB                      # G x B
        tb = BB[j] / np.sqrt(adj * (Sg ** 2).sum(0))
        p_wcb.append(np.mean(np.abs(tb) >= abs(t[j])))
    return pd.DataFrame({"coef": b, "se": se, "t": t, "p_wcb": p_wcb}, index=xs), int(len(d)), len(G)
