import asyncio
import json
import random
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="RAG Mock Server")

# ──────────────────────────────────────────
# Simulasi latency realistis per mode
# Berdasarkan estimasi pipeline L40S + vLLM
# ──────────────────────────────────────────
LATENCY_PROFILE = {
    "chitchat":      (0.3,  0.8),   # (min_s, max_s)
    "cache_hit":     (0.05, 0.15),
    "out_of_scope":  (0.2,  0.5),
    "blocked":       (0.05, 0.1),
    "rag":           (2.5,  8.0),   # paling berat — LLM generation
}

INTENT_WEIGHTS = {
    "rag":          0.40,
    "chitchat":     0.30,
    "cache_hit":    0.15,
    "out_of_scope": 0.10,
    "blocked":      0.05,
}

RAG_ANSWERS = [
    "Untuk mengajukan cuti akademik di UNHAS, mahasiswa harus memenuhi persyaratan berikut: (1) telah menempuh minimal 2 semester, (2) IPK minimal 2.0, (3) mengisi formulir permohonan di Bagian Akademik, dan (4) mendapat persetujuan dari Dosen Wali.",
    "Syarat wisuda di UNHAS meliputi: telah lulus semua mata kuliah dengan total SKS sesuai kurikulum, IPK minimal 2.0, tidak memiliki tanggungan administrasi, dan telah menyelesaikan skripsi/tugas akhir.",
    "Fakultas Teknik UNHAS memiliki beberapa program studi antara lain Teknik Informatika, Teknik Elektro, Teknik Sipil, Teknik Mesin, dan Teknik Arsitektur.",
    "Jadwal kuliah Teknik Informatika semester ini dapat dilihat melalui portal akademik UNHAS di siakad.unhas.ac.id menggunakan NIM dan password Anda.",
    "Kurikulum 2022 Teknik Informatika UNHAS mengharuskan mahasiswa menempuh total 144 SKS yang terdiri dari mata kuliah wajib universitas, fakultas, dan program studi.",
]

CHITCHAT_ANSWERS = [
    "Halo! Ada yang bisa saya bantu seputar akademik UNHAS?",
    "Terima kasih! Senang bisa membantu. Ada pertanyaan lain?",
    "Selamat pagi! Saya siap membantu informasi akademik UNHAS.",
]

SOURCES_MOCK = [
    {
        "file_name": "SOP_Akademik_UNHAS_2023.pdf",
        "page": random.randint(1, 50),
        "score": round(random.uniform(0.75, 0.95), 3),
        "text_preview": "...mahasiswa yang memenuhi persyaratan akademik dapat mengajukan permohonan..."
    },
    {
        "file_name": "Panduan_Akademik_2022.pdf",
        "page": random.randint(1, 80),
        "score": round(random.uniform(0.60, 0.74), 3),
        "text_preview": "...ketentuan ini berlaku bagi seluruh mahasiswa program sarjana..."
    }
]


def pick_mode() -> str:
    """Weighted random intent mode."""
    rand = random.random()
    cumulative = 0.0
    for mode, weight in INTENT_WEIGHTS.items():
        cumulative += weight
        if rand < cumulative:
            return mode
    return "rag"


def simulate_latency(mode: str):
    min_s, max_s = LATENCY_PROFILE.get(mode, (1.0, 3.0))
    time.sleep(random.uniform(min_s, max_s))


def build_response(question: str, mode: str) -> dict:
    start = time.time()
    simulate_latency(mode)
    total_time = round(time.time() - start, 3)

    if mode == "rag":
        answer = random.choice(RAG_ANSWERS)
        sources = SOURCES_MOCK
        top_score = sources[0]["score"]
    elif mode == "chitchat":
        answer = random.choice(CHITCHAT_ANSWERS)
        sources = []
        top_score = None
    elif mode == "cache_hit":
        answer = random.choice(RAG_ANSWERS)
        sources = SOURCES_MOCK
        top_score = SOURCES_MOCK[0]["score"]
    elif mode == "out_of_scope":
        answer = "Maaf, pertanyaan tersebut di luar topik akademik UNHAS yang bisa saya bantu."
        sources = []
        top_score = None
    elif mode == "blocked":
        answer = "Pertanyaan Anda mengandung konten yang tidak dapat saya proses."
        sources = []
        top_score = None
    else:
        answer = "Maaf, saya tidak dapat memproses permintaan ini."
        sources = []
        top_score = None

    return {
        "answer": answer,
        "sources": sources,
        "condensed_question": question if mode == "rag" else None,
        "debug": {
            "mode": mode,
            "total_time_s": total_time,
            "model": "mock-qwen3-vl-8b",
            "top_score": top_score,
        }
    }


# ──────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "services": {
            "llm": "ok",
            "qdrant": "ok",
            "redis": "ok",
            "postgres": "ok",
        }
    }


@app.post("/api/query")
async def query(request: Request):
    body = await request.json()
    question = body.get("question", "")
    mode = pick_mode()
    response = build_response(question, mode)
    return JSONResponse(content=response)


@app.post("/api/query/stream")
async def query_stream(request: Request):
    body = await request.json()
    question = body.get("question", "")

    # Mode stream selalu pakai RAG / chitchat (yang punya token output)
    stream_modes = ["rag", "chitchat", "cache_hit"]
    stream_weights = [0.60, 0.25, 0.15]
    rand = random.random()
    cumulative = 0.0
    mode = "rag"
    for m, w in zip(stream_modes, stream_weights):
        cumulative += w
        if rand < cumulative:
            mode = m
            break

    async def generate():
        # Simulasi TTFT delay (sebelum token pertama)
        ttft_delay = random.uniform(0.3, 1.5)
        await asyncio.sleep(ttft_delay)

        # Pilih answer berdasarkan mode
        if mode == "rag":
            answer = random.choice(RAG_ANSWERS)
        elif mode == "chitchat":
            answer = random.choice(CHITCHAT_ANSWERS)
        else:
            answer = random.choice(RAG_ANSWERS)  # cache_hit sama dengan rag

        # Stream token per token (simulasi vLLM streaming)
        words = answer.split(" ")
        full_answer = ""
        for word in words:
            token = word + " "
            full_answer += token
            event = json.dumps({"type": "token", "delta": token})
            yield f"data: {event}\n\n"
            # Inter-token latency realistis: 30-80ms per token
            await asyncio.sleep(random.uniform(0.03, 0.08))

        # Kirim event meta di akhir (sama seperti API asli)
        meta = json.dumps({
            "type": "meta",
            "answer": full_answer.strip(),
            "sources": SOURCES_MOCK if mode in ("rag", "cache_hit") else [],
            "debug": {
                "mode": mode,
                "total_time_s": round(ttft_delay + len(words) * 0.05, 3),
                "model": "mock-qwen3-vl-8b",
                "top_score": SOURCES_MOCK[0]["score"] if mode in ("rag", "cache_hit") else None,
            }
        })
        yield f"data: {meta}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )