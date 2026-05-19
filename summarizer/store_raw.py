#!/usr/bin/env python3
"""
RAG Load Test — Raw Storage
Menyimpan raw k6 output + metadata lengkap ke file JSON terpisah.
"""

import json
import os
import argparse
import platform
import subprocess
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────
# Metadata skenario
# ──────────────────────────────────────────────────────
SCENARIO_META = {
    "01": {
        "name": "Smoke Test",
        "tujuan": "Validasi endpoint hidup dan schema response sesuai sebelum pengujian serius.",
        "menggambarkan": "1 user mengakses /api/query dan /api/health selama 2 menit tanpa tekanan.",
        "vus_pattern": "1 VU konstan",
        "durasi_target": "2 menit",
        "endpoint": ["/api/query", "/api/health"],
        "metrik_kritis": ["http_req_failed", "checks"],
    },
    "02": {
        "name": "Baseline Intent",
        "tujuan": (
            "Mengukur latency murni per tipe intent (chitchat, rag_short, rag_medium, out_of_scope) "
            "dalam kondisi tanpa beban. Hasil ini menjadi angka referensi untuk skenario 03, 05, 06."
        ),
        "menggambarkan": (
            "1 user bergantian mengirim 4 tipe pertanyaan: sapaan (chitchat), "
            "pertanyaan akademik singkat (rag_short), pertanyaan kompleks (rag_medium), "
            "dan pertanyaan di luar topik (out_of_scope)."
        ),
        "vus_pattern": "1 VU konstan, 20 iterasi",
        "durasi_target": "~5 menit",
        "endpoint": ["/api/query"],
        "metrik_kritis": [
            "baseline_latency_chitchat_ms",
            "baseline_latency_rag_short_ms",
            "baseline_latency_rag_medium_ms",
            "baseline_latency_oos_ms",
        ],
    },
    "03": {
        "name": "Concurrency Sweep",
        "tujuan": (
            "Menemukan kapasitas maksimal server dan titik breaking point "
            "dengan menaikkan VUs secara bertahap dari 1 sampai 40."
        ),
        "menggambarkan": (
            "VUs dinaikkan step-by-step: 1→5→10→15→20→25→30→35→40, "
            "masing-masing 3 menit. Setiap VU mengirim pertanyaan acak dengan "
            "distribusi realistis (40% RAG, 30% chitchat, 20% ambiguous, 10% OOS)."
        ),
        "vus_pattern": "Ramp bertahap 1→40 VUs",
        "durasi_target": "~28 menit",
        "endpoint": ["/api/query"],
        "metrik_kritis": [
            "http_req_duration",
            "http_req_failed",
            "rag_pipeline_total_time_ms",
            "http_reqs",
            "rag_cache_hit",
        ],
    },
    "04": {
        "name": "Stream TTFT",
        "tujuan": (
            "Mengukur Time to First Token (TTFT) — waktu dari request dikirim "
            "sampai karakter pertama jawaban muncul. Ini metrik UX utama chatbot streaming."
        ),
        "menggambarkan": (
            "User menggunakan endpoint /api/query/stream (SSE). "
            "k6 mengukur kapan byte pertama diterima (TTFT) dan kapan event 'meta' "
            "terakhir diterima (total duration). VUs dinaikkan 1→5→10→15."
        ),
        "vus_pattern": "Ramp 1→5→10→15 VUs",
        "durasi_target": "~13 menit",
        "endpoint": ["/api/query/stream"],
        "metrik_kritis": [
            "rag_ttft_ms",
            "stream_success_rate",
            "stream_total_duration_ms",
        ],
    },
    "05": {
        "name": "Spike Test",
        "tujuan": (
            "Menguji ketahanan server terhadap lonjakan traffic tiba-tiba, "
            "simulasi kondisi saat ada pengumuman UNHAS viral atau registrasi massal."
        ),
        "menggambarkan": (
            "Traffic normal 5 VU → spike mendadak ke 50 VU dalam 30 detik → "
            "tahan 2 menit → turun ke 5 VU → observasi recovery → spike kedua 40 VU."
        ),
        "vus_pattern": "5 → spike 50 → 5 → spike 40 → 0",
        "durasi_target": "~10 menit",
        "endpoint": ["/api/query"],
        "metrik_kritis": [
            "http_req_failed",
            "http_req_duration",
            "rag_pipeline_total_time_ms",
        ],
    },
    "06": {
        "name": "Soak Test",
        "tujuan": (
            "Mendeteksi memory leak, connection leak, dan degradasi performa jangka panjang "
            "yang hanya muncul setelah server berjalan lama."
        ),
        "menggambarkan": (
            "10 VU berjalan terus-menerus selama 40 menit dengan request acak berkelanjutan. "
            "Load tidak berat, fokus pada konsistensi dan tren latency dari waktu ke waktu."
        ),
        "vus_pattern": "10 VUs konstan selama 40 menit",
        "durasi_target": "~45 menit",
        "endpoint": ["/api/query"],
        "metrik_kritis": [
            "rag_pipeline_total_time_ms",
            "http_req_failed",
            "rag_cache_hit",
        ],
    },
}

# Skenario yang menyertakan baseline_reference (relevan untuk perbandingan)
SCENARIOS_WITH_BASELINE = {"03", "05", "06"}


# ──────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────
def get_system_info() -> dict:
    info = {
        "os":             platform.system(),
        "os_version":     platform.version(),
        "python_version": platform.python_version(),
        "machine":        platform.machine(),
    }

    # CPU
    try:
        with open("/proc/cpuinfo") as f:
            cpuinfo = f.read()
        model_lines = [l for l in cpuinfo.split("\n") if "model name" in l]
        if model_lines:
            info["cpu_model"] = model_lines[0].split(":")[1].strip()
    except Exception:
        pass
    info["cpu_cores"] = os.cpu_count()

    # RAM
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        total_line = [l for l in meminfo.split("\n") if "MemTotal" in l]
        if total_line:
            kb = int(total_line[0].split()[1])
            info["ram_total_gb"] = round(kb / 1024 / 1024, 1)
    except Exception:
        pass

    # GPU (nvidia-smi)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        info["gpu"] = result.stdout.strip() if result.returncode == 0 else "N/A"
    except Exception:
        info["gpu"] = "N/A"

    return info


def load_baseline() -> dict:
    path = Path("summarizer/baseline.json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RAG Load Test Raw Storage")
    parser.add_argument("--scenario",    required=True, choices=["01","02","03","04","05","06"])
    parser.add_argument("--input",       required=True, help="Path k6 --summary-export JSON")
    parser.add_argument("--session-dir", required=True, help="Output folder untuk raw files")
    parser.add_argument("--rag-url",     default=os.environ.get("RAG_URL", "N/A"))
    parser.add_argument("--influx-url",  default=os.environ.get("INFLUX_URL", "N/A"))
    args = parser.parse_args()

    # Load inputs
    with open(args.input) as f:
        k6_raw = json.load(f)

    scenario_meta = SCENARIO_META.get(args.scenario, {})
    baseline      = load_baseline()
    system_info   = get_system_info()
    now           = datetime.now().isoformat()

    # Bangun raw document
    raw_doc = {
        "_doc_type":    "rag_load_test_raw",
        "_doc_version": "1.0",
        "_generated_at": now,

        "session": {
            "rag_url":     args.rag_url,
            "influx_url":  args.influx_url,
            "session_dir": args.session_dir,
        },

        "scenario": {
            "id":            args.scenario,
            "name":          scenario_meta.get("name"),
            "tujuan":        scenario_meta.get("tujuan"),
            "menggambarkan": scenario_meta.get("menggambarkan"),
            "vus_pattern":   scenario_meta.get("vus_pattern"),
            "durasi_target": scenario_meta.get("durasi_target"),
            "endpoint":      scenario_meta.get("endpoint"),
            "metrik_kritis": scenario_meta.get("metrik_kritis"),
        },

        "execution": {
            "started_at":          now,
            "test_run_duration_ms": k6_raw.get("state", {}).get("testRunDurationMs"),
            "state":               k6_raw.get("state", {}),
        },

        "server_spec": system_info,

        # Hanya disertakan untuk S03, S05, S06
        "baseline_reference": (
            baseline if args.scenario in SCENARIOS_WITH_BASELINE and baseline
            else None
        ),

        "k6_metrics_raw": k6_raw.get("metrics", {}),
    }

    # Simpan
    os.makedirs(args.session_dir, exist_ok=True)
    scenario_name = scenario_meta.get("name", args.scenario).lower().replace(" ", "_")
    out_path = os.path.join(
        args.session_dir,
        f"{args.scenario}_{scenario_name}_raw.json"
    )

    with open(out_path, "w") as f:
        json.dump(raw_doc, f, indent=2, ensure_ascii=False)

    print(f"[store_raw] ✅ Raw saved: {out_path}")


if __name__ == "__main__":
    main()