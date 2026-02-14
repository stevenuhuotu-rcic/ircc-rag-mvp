import os
from openai import OpenAI
import psycopg
from pgvector.psycopg import register_vector
from pgvector import Vector
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
TOP_K = 15

client = OpenAI()

def get_conn():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn

def embed_query(text):
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    )
    return resp.data[0].embedding

def search_similar_chunks(query_embedding):
    # Fetch more than we need, then filter in Python
    FETCH_K = 30
    EXCLUDE_URL = "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html"

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
            (Vector(query_embedding), FETCH_K),
        )
        rows = cur.fetchall()
    conn.close()

    # Filter out the broad index/list page
    filtered = [(u, sec, txt) for (u, sec, txt) in rows if u != EXCLUDE_URL]

    # Return only TOP_K results after filtering
    return filtered[:TOP_K]


def main():
    question = input("Enter your question: ")

    print("\nEmbedding question...")
    embedding = embed_query(question)

    print("Searching vector DB...\n")
    results = search_similar_chunks(embedding)

    for i, (url, section, content) in enumerate(results, 1):
        print(f"\nResult {i}")
        print(f"URL: {url}")
        print(f"Section: {section}")
        print(f"Content preview: {content[:500]}")
        print("-" * 60)

if __name__ == "__main__":
    main()
