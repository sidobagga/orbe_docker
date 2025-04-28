import math
from ..config import client, newsapi

def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x*y for x,y in zip(a,b))
    mag = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b))
    return dot/mag if mag else 0.0

def fetch_related(headline: str, k: int = 10, keep: int = 4) -> str:
    """
    Search NewsAPI for 'headline', embed with OpenAI, score by cosine similarity,
    and return top 'keep' items as Markdown bullets.
    """
    # 1) fetch top-k relevant articles from NewsAPI
    hits = newsapi.get_everything(q=headline, language="en", sort_by="relevancy", page_size=k)["articles"]
    
    # 2) get embedding for the original headline
    resp0 = client.embeddings.create(model="text-embedding-ada-002", input=[headline])
    seed_vec = resp0.data[0].embedding

    scored = []
    for art in hits:
        # 3) embed each candidate title
        resp_i = client.embeddings.create(model="text-embedding-ada-002", input=[art["title"]])
        vec_i = resp_i.data[0].embedding
        sim = cosine_sim(seed_vec, vec_i)
        scored.append((sim, art))
    
    # 4) pick top-N by similarity
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:keep]
    bullets = [f"*{art['source']['name']}* — {art['title']}" for _, art in top]
    return "\n".join(bullets) 