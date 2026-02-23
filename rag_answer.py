import os
from openai import OpenAI
import psycopg
from pgvector.psycopg import register_vector
from pgvector import Vector
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
TOP_K_FETCH = 25
TOP_K_USE = 6  # how many chunks we pass into the model

EXCLUDE_URLS = {
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html"
}

client = OpenAI()

def get_conn():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn

def embed_query(text: str):
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

def retrieve(query: str):
    qvec = embed_query(query)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.url, c.section, c.content
            FROM chunks c
            JOIN sources s ON s.id = c.source_id
            ORDER BY c.embedding <=> %s
            LIMIT %s
            """,
            (Vector(qvec), TOP_K_FETCH),
        )
        rows = cur.fetchall()
    conn.close()

    # filter noisy index pages
    rows = [r for r in rows if r[0] not in EXCLUDE_URLS]
        # Hard allow-list for IMM1295 questions (prevents unrelated programs from leaking in)
    q = query.lower()
    if "imm1295" in q or "imm 1295" in q:
        allow = [
            "guide-5487",
            "imm1295",
            "imm5488",  # checklist
            "imm5707",
            "imm5409",
            "imm5476",
            "imm5475",
        ]
        rows = [r for r in rows if any(a in r[0].lower() for a in allow)]

        # Safety fallback: if filtering becomes too strict, keep the best guide source
        if not rows:
            rows = [r for r in rows if "guide-5487" in r[0].lower()]


    # keep first TOP_K_USE
    return rows[:TOP_K_USE]

def build_context(rows):
    # format context as numbered snippets
    parts = []
    for i, (url, section, content) in enumerate(rows, 1):
        parts.append(f"[{i}] URL: {url}\nSection: {section}\nText: {content}")
    return "\n\n".join(parts)

def answer(query: str, rows):
    context = build_context(rows)

    system = (
        "You are an immigration information assistant. "
        "Use ONLY the provided sources. "
        "If the sources do not support an answer, say so."
    )

    user = f"""
Question:
{query}

Sources:
{context}

Instructions:
- Answer in plain language.
- Use bullet points.
- Include a short 'Forms to submit' list if relevant.
- DO NOT list or mention sources in the answer.
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.output_text

def main():
    query = input("Ask a question: ").strip()
    rows = retrieve(query)
    print("\n--- Retrieved sources ---")
    for (url, section, _) in rows:
        print(f"- {url}  |  {section}")

    print("\n--- Answer ---\n")
    print(answer(query, rows))

if __name__ == "__main__":
    main()
