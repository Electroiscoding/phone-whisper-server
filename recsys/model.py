import torch, torch.nn as nn, torch.nn.functional as nnf

mlp = lambda i, h, o: nn.Sequential(nn.Linear(i, h), nn.ReLU(), nn.Linear(h, o))

class ItemTower(nn.Module):
    def __init__(s, item_in=389, out=128):
        super().__init__(); s.net = mlp(item_in, 256, out)
    def forward(s, x): return nnf.normalize(s.net(x), dim=-1)

class UserTower(nn.Module):
    def __init__(s, item_in=389, aff=15, demo=4, out=128):
        super().__init__(); s.net = mlp(item_in + aff + demo, 256, out)
    def forward(s, aff, hist, demo):
        return nnf.normalize(s.net(torch.cat([aff, hist, demo], -1)), dim=-1)

class TwoTower(nn.Module):
    def __init__(s):
        super().__init__()
        s.user, s.item = UserTower(), ItemTower()
        s.log_scale = nn.Parameter(torch.tensor(2.64))        # learned temperature

    def loss(s, aff, hist, demo, pid, nid, w, F):
        u = s.user(aff, hist, demo)                            # B x 128
        ids = torch.cat([pid, nid])
        lg = (u @ s.item(F[ids]).T) * s.log_scale.exp()        # B x 2B: in-batch + logged skips
        dup = ids[None] == pid[:, None]                        # same post = not a negative
        r = torch.arange(len(u)); dup[r, r] = False
        ce = nnf.cross_entropy(lg.masked_fill(dup, -1e4), r, reduction="none")
        return (ce * w).sum() / w.sum()
