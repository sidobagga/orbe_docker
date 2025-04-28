import os
import logging
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from .config import client, newsapi
from .utils.news_search import fetch_related
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

try:
    import trafilatura
    from trafilatura.settings import use_config
    import httpx
    logger.info("Successfully imported all required packages")
except ImportError as e:
    logger.error(f"Failed to import required packages: {e}")
    raise

# --------------------------------------------------
# Config & init
# --------------------------------------------------
try:
    if not client.api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    logger.info("OpenAI client configured successfully")
    logger.info("NewsAPI client configured successfully")
except Exception as e:
    logger.error(f"Failed to configure clients: {e}")
    raise

app = FastAPI(title="News-Agg MVP")

# Get the current directory in the Vercel environment
try:
    current_dir = Path(__file__).parent
    logger.info(f"Current directory: {current_dir}")
except Exception as e:
    logger.error(f"Failed to get current directory: {e}")
    raise

# Mount static files and templates if they exist
try:
    static_dir = current_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info(f"Static files mounted from: {static_dir}")
    else:
        logger.warning("Static directory not found")

    # Initialize templates
    templates = Jinja2Templates(directory=str(current_dir / "templates"))
    logger.info("Templates initialized successfully")
except Exception as e:
    logger.error(f"Failed to setup static files and templates: {e}")
    raise

class SummReq(BaseModel):
    url: str

# --------------------------------------------------
# Fetch + extract with two-level fallback
# --------------------------------------------------
# 1) Prepare a Trafilatura config that spoofs Chrome UA
try:
    _cfg = use_config(None)
    _cfg.USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
    logger.info("Trafilatura config initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Trafilatura config: {e}")
    raise

def fetch_article(url: str) -> str:
    logger.info(f"Attempting to fetch article from: {url}")
    # Attempt #1: Trafilatura with spoofed UA
    try:
        html = trafilatura.fetch_url(url, config=_cfg)
        if html:
            text = trafilatura.extract(html, include_comments=False, config=_cfg)
            if text:
                logger.info("Successfully fetched article using Trafilatura")
                return text
    except Exception as e:
        logger.warning(f"Trafilatura fetch failed: {e}")

    # Attempt #2: httpx GET with browser UA
    headers = {"User-Agent": _cfg.USER_AGENT}
    try:
        resp = httpx.get(url, headers=headers, timeout=15.0)
        resp.raise_for_status()
        html2 = resp.text
        text2 = trafilatura.extract(html2, include_comments=False, config=_cfg)
        if text2:
            logger.info("Successfully fetched article using httpx")
            return text2
    except Exception as e:
        logger.warning(f"httpx fetch failed: {e}")

    # All attempts failed
    error_msg = "Failed to fetch or extract article"
    logger.error(error_msg)
    raise ValueError(error_msg)

# --------------------------------------------------
# Summarization logic
# --------------------------------------------------
SYSTEM_MSG = """
You are an investigative news analyst.  
Respond in Markdown with sections:
1. **Quick Take** – ≤120 words.  
2. **3 Key Points** – bullet list.  
3. **Other Angles** – bullet list with Outlet & Headline.  
4. **Narrative Map** – 2–3 sentences comparing angles.  
Be concise and factual.
"""

def summarize(article_text: str, headline: str) -> str:
    logger.info("Starting article summarization")
    # truncate and build prompt
    snippet = article_text[:9000]
    related = fetch_related(headline)
    user_msg = (
        f"### Original Article (as of {datetime.utcnow().date()})\n"
        f"{snippet}\n\n"
        f"### Related Snippets\n{related}"
    )

    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.2,
        max_tokens=380,
    )
    summary = resp.choices[0].message.content.strip()
    logger.info("Successfully generated summary")
    return summary

# --------------------------------------------------
# Endpoints
# --------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    logger.info("Handling root GET request")
    try:
        response = templates.TemplateResponse("index.html", {"request": request})
        logger.info("Successfully rendered template")
        return response
    except Exception as e:
        logger.error(f"Failed to render template: {e}")
        raise

@app.post("/summarize")
async def summarize_endpoint(req: SummReq):
    logger.info(f"Handling summarize request for URL: {req.url}")
    try:
        article = fetch_article(req.url)
        # use the first line or meta <title> as headline
        headline = article.split("\n", 1)[0][:120]
        summary = summarize(article, headline)
        logger.info("Successfully processed summarize request")
        return {"summary": summary}
    except Exception as e:
        logger.error(f"Failed to process summarize request: {e}")
        raise HTTPException(status_code=502, detail=str(e)) 