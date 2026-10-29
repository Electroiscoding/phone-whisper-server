import os
import numpy as np
import torch
from recsys.model import ItemTower, UserTower

NC, NS, PER_DAY, DAYS, POOL = 5, 6, 100, 60, 14
CAT_NAMES = ["Tech", "Business", "Arts", "Entertainment", "Sports"]

_rng = np.random.default_rng(0)
KW = [[s.split(",") for s in c] for c in [
 ["graphics cards,chip fabrication,benchmarks,transistors,wafer yields,overclocking",
  "python,rust,compilers,debugging,open source,APIs",
  "AI models,neural networks,chatbots,training data,fine-tuning,inference costs",
  "smartphones,battery life,camera sensors,foldables,iOS,Android updates",
  "cybersecurity,data breaches,passwords,encryption,phishing,zero-days",
  "robots,drones,3D printing,self-driving cars,electric scooters,smart homes"],
 ["startups,seed funding,venture capital,pitch decks,founders,unicorns",
  "stock market,earnings,interest rates,inflation,index funds,bonds",
  "marketing,branding,SEO,growth hacking,ad campaigns,influencers",
  "real estate,mortgages,rental yields,housing market,property flipping,landlords",
  "remote work,productivity,leadership,hiring,burnout,management",
  "crypto,bitcoin,blockchain,wallets,DeFi,token launches"],
 ["oil painting,watercolor,gallery openings,sculpture,art auctions,museums",
  "poetry,novels,book clubs,literary prizes,writing prompts,bestsellers",
  "classical music,jazz,opera,orchestras,vinyl records,live concerts",
  "street photography,film cameras,portraits,darkroom,photo essays,lenses",
  "architecture,interior design,ceramics,textiles,calligraphy,craft fairs",
  "theatre,ballet,contemporary dance,stage design,playwrights,improv"],
 ["blockbuster movies,box office,film trailers,sequels,directors,oscars",
  "streaming series,season finales,binge watching,plot twists,showrunners,spoilers",
  "pop music,album drops,world tours,music videos,charts,collaborations",
  "video games,speedruns,esports,indie games,console launches,game mods",
  "stand-up comedy,memes,sketches,viral videos,pranks,podcasts",
  "celebrity news,red carpet,fan theories,anime,K-pop,reality shows"],
 ["football,transfer window,premier league,goals,managers,derbies",
  "basketball,NBA playoffs,three-pointers,draft picks,dunks,coaching",
  "cricket,IPL,test matches,bowling,batting records,world cup",
  "running,marathons,strength training,calisthenics,cycling,recovery",
  "tennis,grand slams,serve technique,rankings,clay courts,rivalries",
  "formula one,pit stops,qualifying,motorbikes,rally,lap records"]]]

TPL = [
    "{a} and {b}: what {c} changes",
    "Why everyone is talking about {a}",
    "My honest take on {a}, {b} and {c}",
    "{a}, {b}, {c}: a quick breakdown",
    "Behind the scenes of {a} with {b}",
    "Top 5 things to know about {a} and {c}"
]

NI = PER_DAY * DAYS
_cat = _rng.choice(NC, NI, p=[.25, .2, .15, .25, .15])
_sub = _rng.integers(0, NS, NI)
_qual = _rng.lognormal(0, .6, NI)

def _generate_post(c, s):
    w = list(_rng.choice(KW[c][s], 5, replace=False))
    if _rng.random() < .15:
        w[0] = _rng.choice(KW[c][_rng.integers(NS)])
    if _rng.random() < .05:
        w[1] = _rng.choice(KW[_rng.integers(NC)][_rng.integers(NS)])
    return _rng.choice(TPL).format(a=w[0], b=w[1], c=w[2]) + f" Covers {w[3]} and {w[4]} in detail."

TEXTS = [_generate_post(c, s) for c, s in zip(_cat, _sub)]

class RecsysEngine:
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.dirname(__file__)
        data_path = os.path.join(data_dir, "data.pt")
        item_path = os.path.join(data_dir, "item_tower.pt")
        user_path = os.path.join(data_dir, "user_tower.pt")

        data = torch.load(data_path, map_location="cpu", weights_only=False)
        self.F = data["F"]

        self.item_tower = ItemTower(item_in=389, out=128)
        self.user_tower = UserTower(item_in=389, aff=15, demo=4, out=128)
        self.item_tower.load_state_dict(torch.load(item_path, map_location="cpu", weights_only=True))
        self.user_tower.load_state_dict(torch.load(user_path, map_location="cpu", weights_only=True))
        self.item_tower.eval()
        self.user_tower.eval()

        with torch.no_grad():
            self.IV = self.item_tower(self.F)

        self.cat_tensor = self.F[:, :5].argmax(1)
        self.day_tensor = torch.arange(len(self.F)) // PER_DAY
        self.embedder = None

    def rank_posts(self, posts, aff, hist_ids=None, demo=None, top_k=None):
        if not posts:
            return []
        if self.embedder is None:
            from sentence_transformers import SentenceTransformer
            self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        cat_map = {"tech": 0, "business": 1, "arts": 2, "entertainment": 3, "sports": 4}
        texts = [p.get("text", "") for p in posts]
        text_embs = torch.tensor(self.embedder.encode(texts, normalize_embeddings=True))

        cat_one_hot = torch.zeros(len(posts), 5)
        for i, p in enumerate(posts):
            c_val = p.get("category", p.get("category_id", 0))
            if isinstance(c_val, str):
                c_idx = cat_map.get(c_val.lower(), 0)
            else:
                c_idx = int(c_val) if 0 <= int(c_val) < 5 else 0
            cat_one_hot[i, c_idx] = 1.0

        item_feats = torch.cat([cat_one_hot, text_embs], dim=-1)
        with torch.no_grad():
            item_embs = self.item_tower(item_feats)

            aff_t = torch.tensor(aff, dtype=torch.float32)
            demo_t = torch.tensor(demo or [0.0, 1.0, 0.0, 0.0], dtype=torch.float32)
            if hist_ids:
                h = self.F[hist_ids].mean(0)
            else:
                h = torch.zeros(self.F.shape[1])
            u = self.user_tower(aff_t.unsqueeze(0), h.unsqueeze(0), demo_t.unsqueeze(0))[0]

            scores = (item_embs @ u).tolist()

        scored_items = []
        for p, score in zip(posts, scores):
            item = dict(p)
            item["score"] = round(float(score), 4)
            scored_items.append(item)

        scored_items.sort(key=lambda x: x["score"], reverse=True)
        for rank, item in enumerate(scored_items, 1):
            item["rank"] = rank

        if top_k is not None:
            scored_items = scored_items[:top_k]

        return scored_items

    @torch.no_grad()
    def recommend(self, aff, hist_ids=None, demo=None, seen=None, today=59, n=10, fresh=0.01, div=0.05, eps=0.1, posts=None):
        if posts:
            ranked = self.rank_posts(posts, aff=aff, hist_ids=hist_ids, demo=demo, top_k=n)
            status = "warm" if len(hist_ids or []) >= 3 else "cold"
            return {
                "status": "ok",
                "user_status": status,
                "total_recs": len(ranked),
                "posts": ranked
            }

        if hist_ids is None:
            hist_ids = []
        if demo is None:
            demo = [0.0, 1.0, 0.0, 0.0]
        if seen is None:
            seen = []

        aff_t = torch.tensor(aff, dtype=torch.float32)
        demo_t = torch.tensor(demo, dtype=torch.float32)

        if hist_ids:
            h = self.F[hist_ids].mean(0)
        else:
            h = torch.zeros(self.F.shape[1])

        u = self.user_tower(aff_t.unsqueeze(0), h.unsqueeze(0), demo_t.unsqueeze(0))[0]

        ok = (self.day_tensor <= today) & (self.day_tensor >= today - POOL)
        if seen:
            ok[list(seen)] = False

        scores = (self.IV @ u - fresh * (today - self.day_tensor)).masked_fill(~ok, -1e9)
        k = min(200, int(ok.sum()))
        cand = scores.topk(k).indices.tolist()

        out = []
        cnt = torch.zeros(5)

        for _ in range(n):
            if torch.rand(1) < eps:
                pool = ok.clone()
                for o in out:
                    pool[o] = False
                valid = pool.nonzero().squeeze(1)
                if len(valid) == 0:
                    break
                idx = valid[torch.randint(len(valid), (1,))].item()
                out.append(idx)
                cnt[self.cat_tensor[idx]] += 1
                continue

            rem = [c for c in cand if c not in out]
            if not rem:
                break
            best = max(rem, key=lambda c: scores[c].item() - div * cnt[self.cat_tensor[c]].item())
            out.append(best)
            cnt[self.cat_tensor[best]] += 1

        posts_out = [self.get_post(i) for i in out]
        status = "warm" if len(hist_ids) >= 3 else "cold"
        return {
            "status": "ok",
            "user_status": status,
            "total_recs": len(posts_out),
            "posts": posts_out
        }

    def get_post(self, post_id):
        if post_id < 0 or post_id >= NI:
            raise IndexError(f"post_id must be between 0 and {NI - 1}")
        cat_id = int(self.cat_tensor[post_id])
        return {
            "id": post_id,
            "text": TEXTS[post_id],
            "category": CAT_NAMES[cat_id],
            "category_id": cat_id,
            "day": int(self.day_tensor[post_id]),
            "quality": round(float(_qual[post_id]), 3)
        }

    def stats(self):
        return {
            "status": "ok",
            "model": "two-tower-recsys",
            "version": "1.0",
            "posts_indexed": NI,
            "embedding_dim": 128,
            "device": "cpu",
            "categories": CAT_NAMES
        }

_instance = None

def get_recsys_engine():
    global _instance
    if _instance is None:
        _instance = RecsysEngine()
    return _instance
