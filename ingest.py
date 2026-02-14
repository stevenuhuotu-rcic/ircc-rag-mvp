import os
import re
import hashlib
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

import psycopg
from pgvector.psycopg import register_vector
from openai import OpenAI
from dotenv import load_dotenv
from pypdf import PdfReader
import io

# Load .env (OPENAI_API_KEY, DATABASE_URL)
load_dotenv()

EMBED_MODEL = "text-embedding-3-small"   # vector(1536) in DB
CHUNK_MAX_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 120
EMBED_BATCH_SIZE = 32
REQUEST_TIMEOUT = 30

client = OpenAI()

# --------- utilities ----------
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def count_tokens(text: str) -> int:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))

def split_by_tokens(text: str, max_tokens: int, overlap: int) -> List[str]:
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start = max(0, end - overlap)
    return chunks

def is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")

def fetch_bytes(url: str) -> bytes:
    r = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "ircc-rag-bot/0.1"},
    )
    r.raise_for_status()
    return r.content

# --------- extraction ----------
@dataclass
class ExtractedDoc:
    url: str
    title: Optional[str]
    sections: List[Tuple[str, str]]  # (heading, text)
    content_hash: str

def clean_html_to_sections(html: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None
    body = soup.body or soup

    sections: List[Tuple[str, str]] = []
    current_heading = "Intro"
    buf: List[str] = []

    def flush():
        nonlocal buf, current_heading
        txt = " ".join(buf).strip()
        txt = re.sub(r"\s+", " ", txt)
        if txt and len(txt) > 80:
            sections.append((current_heading, txt))
        buf = []

    for el in body.find_all(["h1", "h2", "h3", "p", "li", "table"], recursive=True):
        name = el.name.lower()
        if name in ("h1", "h2", "h3"):
            flush()
            current_heading = el.get_text(" ", strip=True)[:180] or "Section"
        elif name == "table":
            t = el.get_text(" ", strip=True)
            if t:
                buf.append(t)
        else:
            t = el.get_text(" ", strip=True)
            if t:
                buf.append(t)

    flush()
    return title, sections

def extract_document(url: str) -> ExtractedDoc:
    data = fetch_bytes(url)

    # If it's a PDF (by URL or file signature), extract PDF text
    if is_pdf_url(url) or data[:4] == b"%PDF":
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                pages.append((f"Page {i+1}", text))

        title = None
        try:
            title = reader.metadata.title if reader.metadata else None
        except Exception:
            pass

        full_text = "\n\n".join(t for _, t in pages)
        content_hash = sha256(full_text)
        return ExtractedDoc(url=url, title=title, sections=pages, content_hash=content_hash)

    # Otherwise treat as HTML
    html = data.decode("utf-8", errors="ignore")
    title, sections = clean_html_to_sections(html)
    full_text = "\n\n".join(f"{h}\n{t}" for h, t in sections)
    content_hash = sha256(full_text)
    return ExtractedDoc(url=url, title=title, sections=sections, content_hash=content_hash)


# --------- chunking ----------
@dataclass
class Chunk:
    section: str
    content: str
    chunk_index: int
    chunk_hash: str

def chunk_sections(sections: List[Tuple[str, str]]) -> List[Chunk]:
    chunks: List[Chunk] = []
    idx = 0
    for heading, text in sections:
        parts = split_by_tokens(text, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS)
        for p in parts:
            p = re.sub(r"\s+", " ", p).strip()
            if len(p) < 140:
                continue
            chash = sha256(heading + "::" + p)
            chunks.append(Chunk(section=heading, content=p, chunk_index=idx, chunk_hash=chash))
            idx += 1
    return chunks

# --------- DB ----------
def get_conn():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL missing (check your .env)")
    conn = psycopg.connect(db_url)
    register_vector(conn)
    return conn

def upsert_source(conn, doc: ExtractedDoc, doc_type="IRCC", program=None) -> Tuple[int, bool]:
    """
    Returns (source_id, changed)
    changed=True => content changed/new => reinsert chunks
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, content_hash FROM sources WHERE url=%s", (doc.url,))
        row = cur.fetchone()

        if row:
            source_id, old_hash = row
            if old_hash == doc.content_hash:
                return int(source_id), False

            cur.execute(
                "UPDATE sources SET title=%s, doc_type=%s, program=%s, content_hash=%s, retrieved_at=now() WHERE id=%s",
                (doc.title, doc_type, program, doc.content_hash, source_id),
            )
            cur.execute("DELETE FROM chunks WHERE source_id=%s", (source_id,))
            return int(source_id), True

        cur.execute(
            "INSERT INTO sources (url, title, doc_type, program, content_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (doc.url, doc.title, doc_type, program, doc.content_hash),
        )
        source_id = cur.fetchone()[0]
        return int(source_id), True

def embed_texts(texts: List[str]) -> List[List[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def insert_chunks(conn, source_id: int, chunks: List[Chunk]) -> int:
    inserted = 0
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i:i+EMBED_BATCH_SIZE]
        vectors = embed_texts([c.content for c in batch])

        rows = []
        for c, vec in zip(batch, vectors):
            rows.append((source_id, c.chunk_index, c.section, c.content, c.chunk_hash, vec))

        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (source_id, chunk_index, section, content, chunk_hash, embedding)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_id, chunk_hash) DO NOTHING
                """,
                rows,
            )
            inserted += cur.rowcount
        conn.commit()
    return inserted

# --------- run ----------
def load_urls(path="sources.txt") -> List[str]:
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            u = line.strip()
            if u and not u.startswith("#"):
                urls.append(u)
    return urls

def main():
    urls = load_urls()
    if not urls:
        raise RuntimeError("sources.txt is empty")

    conn = get_conn()
    try:
        for url in urls:
            print(f"\n--- Ingesting: {url}")
            doc = extract_document(url)
            chunks = chunk_sections(doc.sections)

            source_id, changed = upsert_source(conn, doc, doc_type="IRCC", program=None)
            conn.commit()

            if not changed:
                print("No change detected (hash match). Skipping.")
                continue

            n = insert_chunks(conn, source_id, chunks)
            print(f"Prepared chunks: {len(chunks)} | Inserted: {n}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
