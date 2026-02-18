import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

import rag_answer

load_dotenv()

app = FastAPI(title="IRCC RAG API", version="0.1")

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    q = req.question.strip()
    if not q:
        return {"answer": "Please ask a question."}

    rows = rag_answer.retrieve(q)
    answer_text = rag_answer.answer(q, rows)
    return {"answer": answer_text}
