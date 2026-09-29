# DocuMind

Retrieval-augmented Q&A over your documents. Upload PDF, TXT or MD files, ask questions, get answers with page-level source citations.

**Stack:** React (Vite), FastAPI, ChromaDB (local embeddings), Groq-hosted Llama 3.3 via OpenAI-compatible API.

## Run locally
Get a free key at console.groq.com.

Backend
    cd backend
    pip install -r requirements.txt
    export GROQ_API_KEY=gsk_...        # PowerShell: $env:GROQ_API_KEY="gsk_..."
    uvicorn main:app --reload

Frontend
    cd frontend
    npm install
    npm run dev                        # http://localhost:5173

Sample documents in backend/samples are indexed automatically on first start.
Try: "How many days of annual leave do I get?" or "How fast must a lost laptop be reported?"

## Deploy (free)
- Backend: Render (render.yaml included). Set GROQ_API_KEY and ALLOWED_ORIGINS (your Vercel URL).
- Frontend: Vercel, root directory `frontend`, env var VITE_API = your Render URL.

## Known limits
- Fixed-size character chunking (900 chars, 150 overlap)
- No auth, one shared collection (not multi-tenant)
- Scanned PDFs without a text layer are rejected
- Free hosting sleeps when idle and has ephemeral disk, so uploads reset on restart (samples are re-indexed)
