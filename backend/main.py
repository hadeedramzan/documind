import io, os, re, uuid
from pathlib import Path

import chromadb
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI  # OpenAI-compatible client, pointed at Groq (free tier)
from pydantic import BaseModel
from pypdf import PdfReader

app = FastAPI(title="DocuMind")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

client = chromadb.PersistentClient(path="./store")
col = client.get_or_create_collection("docs")

llm = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", "missing"),
    base_url="https://api.groq.com/openai/v1",
)
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

SYSTEM = (
    "You answer questions using ONLY the numbered context passages. "
    "Cite sources inline using plain ASCII brackets like [1] or [2]. Use short plain text, bold only if needed. If the answer is not in the context, "
    "say you could not find it in the uploaded documents. Do not guess."
)


def units(text: str, size: int):
    """Yield paragraphs; oversized paragraphs are split on sentence boundaries."""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            yield para
        else:
            for sent in re.split(r"(?<=[.!?])\s+", para):
                for i in range(0, len(sent), size):
                    yield sent[i:i + size]


def chunk(text: str, size: int = 900):
    """Paragraph-aware chunks; markdown headings are carried into each chunk."""
    out, buf, heading = [], "", ""
    text = re.sub(r"^(#{1,6} .*)$", r"\n\1\n", text, flags=re.M)  # headings become own units

    def flush():
        nonlocal buf
        if buf.strip():
            out.append((heading + "\n" if heading else "") + buf.strip())
        buf = ""

    for u in units(text, size):
        if u.startswith("#") and "\n" not in u:
            flush()
            heading = u
            continue
        if buf and len(buf) + len(u) + 2 > size:
            flush()
        buf += u + "\n\n"
    flush()
    return out


def read_pages(name: str, raw: bytes):
    n = name.lower()
    if n.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw))
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
    if n.endswith((".txt", ".md")):
        return [(1, raw.decode("utf-8", "ignore"))]
    raise HTTPException(400, "Only PDF, TXT, MD supported")


def index_file(name: str, raw: bytes) -> int:
    ids, docs, metas = [], [], []
    for page_no, text in read_pages(name, raw):
        for c in chunk(text.strip()):
            if len(c.strip()) < 30:
                continue
            ids.append(str(uuid.uuid4()))
            docs.append(c)
            metas.append({"source": name, "page": page_no})
    if not docs:
        raise HTTPException(400, "No extractable text (scanned PDF?)")
    col.add(ids=ids, documents=docs, metadatas=metas)  # embedded locally by Chroma
    return len(docs)


def load_samples():
    for f in sorted(Path("samples").glob("*")):
        if f.suffix.lower() in (".pdf", ".txt", ".md"):
            index_file(f.name, f.read_bytes())


@app.on_event("startup")
def startup():
    # Free hosting has ephemeral disk, so re-seed demo docs if store is empty
    if col.count() == 0:
        load_samples()


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    name = file.filename or "file"
    return {"file": name, "chunks": index_file(name, raw)}


class Ask(BaseModel):
    question: str


@app.post("/ask")
def ask(body: Ask):
    if col.count() == 0:
        raise HTTPException(400, "Upload a document first")
    res = col.query(query_texts=[body.question], n_results=5)
    docs, metas = res["documents"][0], res["metadatas"][0]
    context = "\n\n".join(
        f"[{i + 1}] ({m['source']}, p.{m['page']})\n{d}"
        for i, (d, m) in enumerate(zip(docs, metas))
    )
    try:
        out = llm.chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {body.question}"},
            ],
        )
    except Exception as e:
        raise HTTPException(502, f"LLM error: {e}")
    answer = out.choices[0].message.content or ""
    answer = re.sub(r"[【\[](\d+)[】\]]", r"[\1]", answer)  # normalise citation style
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 1 <= int(n) <= len(docs)})
    return {
        "answer": answer,
        "sources": [
            {"id": i, "source": metas[i - 1]["source"], "page": metas[i - 1]["page"],
             "snippet": docs[i - 1][:280]}
            for i in cited
        ],
    }


@app.get("/files")
def files():
    metas = col.get(include=["metadatas"])["metadatas"]
    return sorted({m["source"] for m in metas})


@app.delete("/reset")
def reset():
    global col
    client.delete_collection("docs")
    col = client.get_or_create_collection("docs")
    load_samples()
    return {"ok": True}
