import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

import rag_answer

load_dotenv()

app = FastAPI(title="IRCC RAG API", version="0.1")
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str

from typing import List

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []

@app.get("/health")
def health():
    return {"status": "ok"}
@app.get("/healthz")
def healthz():
    return {"status": "ok"}
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    q = req.question.strip()
    if not q:
        return {"answer": "Please ask a question.", "sources": []}

    rows = rag_answer.retrieve(q)

    # Extract source URLs from retrieval rows
    sources = []
    try:
        for r in rows:
            # If retrieve() returns dictionaries
            if isinstance(r, dict):
                src = r.get("source") or r.get("url") or r.get("document_url")
                if src:
                    sources.append(src)

            # If retrieve() returns tuples/lists
            elif isinstance(r, (list, tuple)):
                for item in r:
                    if isinstance(item, str) and item.startswith("http"):
                        sources.append(item)

    except Exception:
        sources = []

    # Remove duplicates while keeping order
    seen = set()
    sources = [s for s in sources if not (s in seen or seen.add(s))]

    answer_text = rag_answer.answer(q, rows)

    return {
        "answer": answer_text,
        "sources": sources
    }
# trigger render redeploy
