import os
import json
import urllib.request
import hashlib
import numpy as np

try:
    import torch
    HAVE_TORCH = True
except ImportError:
    torch = None
    HAVE_TORCH = False

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

def _relu(x):
    return np.maximum(x, 0.0)

def _l2_norm(x):
    norm = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.maximum(norm, 1e-12)

_TEXT_EMB_CACHE = {}
_MAX_CACHE_SIZE = 10000

def _compute_projection_embedding(text: str, dim: int = 384) -> np.ndarray:
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    if not words:
        return vec
    for pos, w in enumerate(words):
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
        idx1 = h % dim
        idx2 = (h >> 9) % dim
        sign = 1.0 if (h & 1) else -1.0
        pos_weight = 1.0 / (1.0 + 0.05 * pos)
        vec[idx1] += sign * pos_weight
        vec[idx2] += (sign * 0.5) * pos_weight
    norm = np.linalg.norm(vec)
    if norm > 1e-12:
        vec /= norm
    return vec

class RecsysEngine:
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.dirname(__file__)

        npz_path = os.path.join(data_dir, "weights.npz")
        if os.path.exists(npz_path):
            w = np.load(npz_path)
            self.it_w0 = w["it_w0"]
            self.it_b0 = w["it_b0"]
            self.it_w2 = w["it_w2"]
            self.it_b2 = w["it_b2"]
            self.ut_w0 = w["ut_w0"]
            self.ut_b0 = w["ut_b0"]
            self.ut_w2 = w["ut_w2"]
            self.ut_b2 = w["ut_b2"]
            self.F = w["F"]
        elif HAVE_TORCH:
            data_path = os.path.join(data_dir, "data.pt")
            item_path = os.path.join(data_dir, "item_tower.pt")
            user_path = os.path.join(data_dir, "user_tower.pt")
            data = torch.load(data_path, map_location="cpu", weights_only=False)
            self.F = data["F"].detach().cpu().numpy()
            it_sd = torch.load(item_path, map_location="cpu", weights_only=True)
            ut_sd = torch.load(user_path, map_location="cpu", weights_only=True)
            self.it_w0 = it_sd["net.0.weight"].detach().cpu().numpy()
            self.it_b0 = it_sd["net.0.bias"].detach().cpu().numpy()
            self.it_w2 = it_sd["net.2.weight"].detach().cpu().numpy()
            self.it_b2 = it_sd["net.2.bias"].detach().cpu().numpy()
            self.ut_w0 = ut_sd["net.0.weight"].detach().cpu().numpy()
            self.ut_b0 = ut_sd["net.0.bias"].detach().cpu().numpy()
            self.ut_w2 = ut_sd["net.2.weight"].detach().cpu().numpy()
            self.ut_b2 = ut_sd["net.2.bias"].detach().cpu().numpy()
        else:
            raise FileNotFoundError(f"Neither weights.npz nor PyTorch weights found in {data_dir}")

        self.IV = self.forward_item(self.F)
        self.cat_array = self.F[:, :5].argmax(1)
        self.day_array = np.arange(len(self.F)) // PER_DAY
        self.embedder = None

    def forward_item(self, x):
        h = _relu(x @ self.it_w0.T + self.it_b0)
        o = h @ self.it_w2.T + self.it_b2
        return _l2_norm(o)

    def forward_user(self, aff, hist, demo):
        if aff.ndim == 1:
            aff = aff[np.newaxis, :]
        if hist.ndim == 1:
            hist = hist[np.newaxis, :]
        if demo.ndim == 1:
            demo = demo[np.newaxis, :]
        x = np.concatenate([aff, hist, demo], axis=-1)
        h = _relu(x @ self.ut_w0.T + self.ut_b0)
        o = h @ self.ut_w2.T + self.ut_b2
        return _l2_norm(o)

    def _get_text_embeddings(self, texts):
        global _TEXT_EMB_CACHE
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)

        results = []
        uncached_indices = []
        uncached_texts = []

        for i, t in enumerate(texts):
            clean_t = (t or "").strip()
            if clean_t in _TEXT_EMB_CACHE:
                results.append(_TEXT_EMB_CACHE[clean_t])
            else:
                results.append(None)
                uncached_indices.append(i)
                uncached_texts.append(clean_t)

        if uncached_indices:
            use_embedder = False
            if os.environ.get("USE_SENTENCE_TRANSFORMER") == "1":
                if self.embedder is not None:
                    use_embedder = True
                elif HAVE_TORCH:
                    try:
                        from sentence_transformers import SentenceTransformer
                        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
                        use_embedder = True
                    except Exception:
                        self.embedder = None

            if use_embedder:
                try:
                    embs = self.embedder.encode(uncached_texts, normalize_embeddings=True)
                    for idx, ct, emb in zip(uncached_indices, uncached_texts, embs):
                        v = np.array(emb, dtype=np.float32)
                        _TEXT_EMB_CACHE[ct] = v
                        results[idx] = v
                except Exception:
                    use_embedder = False

            if not use_embedder:
                for idx, ct in zip(uncached_indices, uncached_texts):
                    v = _compute_projection_embedding(ct, dim=384)
                    _TEXT_EMB_CACHE[ct] = v
                    results[idx] = v

            if len(_TEXT_EMB_CACHE) > _MAX_CACHE_SIZE:
                _TEXT_EMB_CACHE = dict(list(_TEXT_EMB_CACHE.items())[_MAX_CACHE_SIZE // 2:])

        arr = np.array(results, dtype=np.float32)
        return _l2_norm(arr)

    def rank_posts(self, posts, aff, hist_ids=None, demo=None, top_k=None):
        if not posts:
            return []

        cat_map = {"tech": 0, "business": 1, "arts": 2, "entertainment": 3, "sports": 4}
        texts = [p.get("text", "") for p in posts]
        text_embs = self._get_text_embeddings(texts)

        cat_one_hot = np.zeros((len(posts), 5), dtype=np.float32)
        for i, p in enumerate(posts):
            c_val = p.get("category", p.get("category_id", 0))
            if isinstance(c_val, str):
                c_idx = cat_map.get(c_val.lower(), 0)
            else:
                c_idx = int(c_val) if 0 <= int(c_val) < 5 else 0
            cat_one_hot[i, c_idx] = 1.0

        item_feats = np.concatenate([cat_one_hot, text_embs], axis=-1)
        item_embs = self.forward_item(item_feats)

        aff_arr = np.array(aff, dtype=np.float32)
        demo_arr = np.array(demo or [0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        if hist_ids:
            h = self.F[hist_ids].mean(axis=0)
        else:
            h = np.zeros(self.F.shape[1], dtype=np.float32)

        u = self.forward_user(aff_arr, h, demo_arr)[0]
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

    def recommend(self, aff, hist_ids=None, demo=None, seen=None, today=59, n=10, fresh=0.01, div=0.05, eps=0.1, posts=None):
        if posts:
            ranked = self.rank_posts(posts, aff=aff, hist_ids=hist_ids, demo=demo, top_k=n)
            status = "warm" if len(hist_ids or []) >= 3 else "cold"
            return {
                "status": "ok",
                "user_status": status,
                "total_recs": len(ranked),
                "count": len(ranked),
                "posts": ranked,
                "items": ranked
            }

        if hist_ids is None:
            hist_ids = []
        if demo is None:
            demo = [0.0, 1.0, 0.0, 0.0]
        if seen is None:
            seen = []

        aff_arr = np.array(aff, dtype=np.float32)
        demo_arr = np.array(demo, dtype=np.float32)

        if hist_ids:
            h = self.F[hist_ids].mean(axis=0)
        else:
            h = np.zeros(self.F.shape[1], dtype=np.float32)

        u = self.forward_user(aff_arr, h, demo_arr)[0]

        ok = (self.day_array <= today) & (self.day_array >= today - POOL)
        if seen:
            for s in seen:
                if 0 <= s < len(ok):
                    ok[s] = False

        scores = (self.IV @ u - fresh * (today - self.day_array))
        scores[~ok] = -1e9
        k = min(200, int(ok.sum()))
        cand = np.argsort(scores)[-k:][::-1].tolist()

        out = []
        cnt = np.zeros(5, dtype=np.float32)

        for _ in range(n):
            if np.random.rand() < eps:
                pool = ok.copy()
                for o in out:
                    pool[o] = False
                valid = np.where(pool)[0]
                if len(valid) == 0:
                    break
                idx = int(np.random.choice(valid))
                out.append(idx)
                cnt[self.cat_array[idx]] += 1
                continue

            rem = [c for c in cand if c not in out]
            if not rem:
                break
            best = max(rem, key=lambda c: scores[c] - div * cnt[self.cat_array[c]])
            out.append(best)
            cnt[self.cat_array[best]] += 1

        posts_out = [self.get_post(i) for i in out]
        status = "warm" if len(hist_ids) >= 3 else "cold"
        return {
            "status": "ok",
            "user_status": status,
            "total_recs": len(posts_out),
            "posts": posts_out,
            "items": posts_out
        }

    def get_post(self, post_id):
        if post_id < 0 or post_id >= NI:
            raise IndexError(f"post_id must be between 0 and {NI - 1}")
        cat_id = int(self.cat_array[post_id])
        return {
            "id": post_id,
            "text": TEXTS[post_id],
            "category": CAT_NAMES[cat_id],
            "category_id": cat_id,
            "day": int(self.day_array[post_id]),
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

