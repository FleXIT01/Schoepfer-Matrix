"""rerank-server — BGE-Reranker-v2-m3 als HTTP-Dienst für WeKnora.

Cross-Encoder-Reranker, der WeKnoras erwartetes Format bedient:
  POST /rerank   {query, documents:[...]}  ->  {results:[{index, document:{text}, score}]}

Modell: BAAI/bge-reranker-v2-m3 (lädt beim ersten Start ~2.3 GB von HuggingFace).
Default-Gerät CPU, um VRAM-Konflikte mit dem 14-GB-Ollama-Modell zu vermeiden
(Reranking von ~10-20 Treffern ist auf CPU schnell genug). Via RERANK_DEVICE=cuda
umstellbar, wenn genug VRAM frei ist.

Start:  python server.py   (Port 8011)
"""
from __future__ import annotations

import gc
import os
from typing import List

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForSequenceClassification, AutoTokenizer

_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
_DEVICE = os.environ.get("RERANK_DEVICE", "cpu")
_PORT = int(os.environ.get("RERANK_PORT", "8011"))


class RerankRequest(BaseModel):
    query: str
    documents: List[str]


class DocumentInfo(BaseModel):
    text: str


class RankResult(BaseModel):
    index: int
    document: DocumentInfo
    score: float


class FinalResponse(BaseModel):
    results: List[RankResult]


print(f"[rerank] lade Modell {_MODEL} auf {_DEVICE} (erster Start lädt ~2.3 GB)…")
device = torch.device(_DEVICE if (_DEVICE != "cuda" or torch.cuda.is_available()) else "cpu")
tokenizer = AutoTokenizer.from_pretrained(_MODEL)
model = AutoModelForSequenceClassification.from_pretrained(_MODEL)
model.to(device)
model.eval()
print(f"[rerank] Modell geladen auf {device}. Bereit auf Port {_PORT}.")

app = FastAPI(title="BGE-Reranker-v2 für WeKnora", version="1.0.0")


@app.get("/")
def root():
    return {"status": "ok", "model": _MODEL, "device": str(device)}


@app.post("/rerank", response_model=FinalResponse)
def rerank(req: RerankRequest):
    if not req.documents:
        return {"results": []}
    pairs = [[req.query, d] for d in req.documents]
    with torch.no_grad():
        inputs = outputs = logits = None
        try:
            inputs = tokenizer(pairs, padding=True, truncation=True,
                               return_tensors="pt", max_length=1024).to(device)
            outputs = model(**inputs, return_dict=True)
            logits = outputs.logits.view(-1).float()
            scores = torch.sigmoid(logits)
        finally:
            del inputs, outputs, logits
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    results = [
        RankResult(index=i, document=DocumentInfo(text=t), score=float(s.item()))
        for i, (t, s) in enumerate(zip(req.documents, scores))
    ]
    results.sort(key=lambda x: x.score, reverse=True)
    return {"results": results}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=_PORT, log_level="warning")
