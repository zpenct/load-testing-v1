#!/usr/bin/env python3
"""
RAG Load Test Summarizer
Membaca output JSON dari k6 --summary-export dan generate laporan Markdown gabungan.
"""

import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

BASELINE_FILE = "summarizer/baseline.json"
REPORT_FILE   = "reports/load_test_report_{}.md".format(
    datetime.now().strftime("%Y%m%d_%H%M%S")
)

# ──────────────────────────────────────────────────────
# Threshold definitions
# ──────────────────────────────────────────────────────
THRESHOLDS = {
    "error_rate_pct":          {"green": 1.0,  "yellow": 5.0},
    "cpu_pct":                 {"green": 70.0, "yellow": 85.0},
    "ttft_p95_ms":             {"green": 1000, "yellow": 3000},
    "stream_success_rate_pct": {"green": 97.0, "yellow": 95.0},
    "degradation_ratio":       {"green": 1.5,  "yellow": 3.0},
}

def status_icon(value, metric_key, invert=False):
    """Return emoji status berdasarkan threshold."""
    t = THRESHOLDS.get(metric_key)
    if not t:
        return "⚪"
    if not invert:
        if value <= t["green"]:  return "✅"
        if value <= t["yellow"]: return "⚠️"
        return "❌"
    else:
        # Untuk metric di mana lebih tinggi = lebih baik (stream_success_rate)
        if value >= t["green"]:  return "✅"
        if value >= t["yellow"]: return "⚠️"
        return "❌"

def fmt_ms(val):
    if val is None: return "N/A"
    if val >= 1000: return f"{val/1000:.2f}s"
    return f"{val:.0f}ms"

def fmt_pct(val):
    if val is None: return "N/A"
    return f"{val:.2f}%"

def safe_get(data, *keys, default=None):
    """Safely navigate nested dict."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default

# ──────────────────────────────────────────────────────
# Parse k6 summary JSON
# ──────────────────────────────────────────────────────
def parse_k6_summary(path: str) -> dict:
    with open(path) as f:
        raw = json.load(f)

    metrics = raw.get("metrics", {})

    def metric(name, stat="avg"):
        m = metrics.get(name, {})
        # Coba ambil langsung dari root dulu (k6 v0.55+)
        # Fallback ke nested "values" untuk kompatibilitas versi lama
        if stat in m:
            return m.get(stat)
        return m.get("values", {}).get(stat)

    return {
        # Standard k6 metrics
        "http_req_duration_avg":    metric("http_req_duration", "avg"),
        "http_req_duration_p95":    metric("http_req_duration", "p(95)"),
        "http_req_duration_p99":    metric("http_req_duration", "p(99)"),
        "http_req_duration_max":    metric("http_req_duration", "max"),
        "http_req_failed_rate":     metric("http_req_failed", "rate"),
        "http_reqs_count":          metric("http_reqs", "count"),
        "http_reqs_rate":           metric("http_reqs", "rate"),
        "vus_max":                  metric("vus_max", "max"),
        "iterations":               metric("iterations", "count"),

        # Custom RAG metrics
        "rag_pipeline_avg":         metric("rag_pipeline_total_time_ms", "avg"),
        "rag_pipeline_p95":         metric("rag_pipeline_total_time_ms", "p(95)"),
        "rag_cache_hit_rate":       metric("rag_cache_hit", "rate"),
        "rag_error_rate":           metric("rag_error_rate", "rate"),
        "rag_ttft_p95":             metric("rag_ttft_ms", "p(95)"),
        "rag_ttft_avg":             metric("rag_ttft_ms", "avg"),
        "stream_success_rate":      metric("stream_success_rate", "rate"),
        "stream_total_p95":         metric("stream_total_duration_ms", "p(95)"),

        # Intent distribution
        "mode_rag":                 metric("rag_mode_rag", "count"),
        "mode_chitchat":            metric("rag_mode_chitchat", "count"),
        "mode_oos":                 metric("rag_mode_out_of_scope", "count"),
        "mode_blocked":             metric("rag_mode_blocked", "count"),

        # Baseline-specific
        "baseline_chitchat_avg":    metric("baseline_latency_chitchat_ms", "avg"),
        "baseline_chitchat_p95":    metric("baseline_latency_chitchat_ms", "p(95)"),
        "baseline_rag_short_avg":   metric("baseline_latency_rag_short_ms", "avg"),
        "baseline_rag_short_p95":   metric("baseline_latency_rag_short_ms", "p(95)"),
        "baseline_rag_medium_avg":  metric("baseline_latency_rag_medium_ms", "avg"),
        "baseline_rag_medium_p95":  metric("baseline_latency_rag_medium_ms", "p(95)"),
        "baseline_oos_avg":         metric("baseline_latency_oos_ms", "avg"),
        "baseline_oos_p95":         metric("baseline_latency_oos_ms", "p(95)"),
    }

# ──────────────────────────────────────────────────────
# Load / Save baseline
# ──────────────────────────────────────────────────────
def save_baseline(data: dict):
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    baseline = {
        "chitchat_p95":    data.get("baseline_chitchat_p95"),
        "rag_short_p95":   data.get("baseline_rag_short_p95"),
        "rag_medium_p95":  data.get("baseline_rag_medium_p95"),
        "oos_p95":         data.get("baseline_oos_p95"),
        "pipeline_p95":    data.get("rag_pipeline_p95"),
        "saved_at":        datetime.now().isoformat(),
    }
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)
    print(f"[summarizer] ✅ Baseline saved to {BASELINE_FILE}")
    return baseline

def load_baseline() -> dict:
    if not Path(BASELINE_FILE).exists():
        return {}
    with open(BASELINE_FILE) as f:
        return json.load(f)

def degradation(current, baseline_val):
    """Hitung rasio degradasi. Return None jika baseline tidak ada."""
    if not baseline_val or not current:
        return None
    return current / baseline_val

# ──────────────────────────────────────────────────────
# Section generators per skenario
# ──────────────────────────────────────────────────────
def section_smoke(d: dict) -> str:
    err   = (d["http_req_failed_rate"] or 0) * 100
    icon  = status_icon(err, "error_rate_pct")
    total = d["http_reqs_count"] or 0
    p95   = d["http_req_duration_p95"]

    verdict = "✅ **LULUS** — Endpoint sehat, lanjut ke skenario berikutnya." \
        if err < 1 else "❌ **GAGAL** — Ada error, periksa server sebelum melanjutkan."

    cache_pct = (d["rag_cache_hit_rate"] or 0) * 100

    md = f"""
## 🔵 Skenario 01 — Smoke Test

> **Tujuan:** Validasi endpoint hidup dan schema response sesuai.

### Hasil Utama

| Metrik | Nilai | Status |
|---|---|---|
| Total Request | {total} | — |
| Error Rate | {fmt_pct(err)} | {icon} |
| p95 Latency | {fmt_ms(p95)} | — |
| Cache Hit Rate | {fmt_pct(cache_pct)} | — |

### Intent Distribution
"""
    total_intent = sum(filter(None, [
        d["mode_rag"], d["mode_chitchat"], d["mode_oos"], d["mode_blocked"]
    ])) or 1
    for mode, val in [("RAG", d["mode_rag"]), ("Chitchat", d["mode_chitchat"]),
                      ("Out of Scope", d["mode_oos"]), ("Blocked", d["mode_blocked"])]:
        v = val or 0
        pct = v / total_intent * 100
        md += f"- **{mode}:** {v} request ({pct:.1f}%)\n"

    md += f"""
### Verdict
{verdict}

> 💡 **Interpretasi Cache Hit {fmt_pct(cache_pct)}:**
> {"Cache masih dingin (normal di smoke test)." if cache_pct < 20 else "Cache sudah warm — pertanyaan serupa pernah diproses sebelumnya."}
"""
    return md


def section_baseline(d: dict, baseline: dict) -> str:
    def row(label, avg_val, p95_val):
        note = ""
        if avg_val and p95_val:
            ratio = p95_val / avg_val if avg_val else 0
            note = "Variance tinggi ⚠️" if ratio > 3 else "Stabil ✅"
        return f"| {label} | {fmt_ms(avg_val)} | {fmt_ms(p95_val)} | {note} |"

    md = f"""
## 🟡 Skenario 02 — Baseline Intent

> **Tujuan:** Ukur latency murni per tipe intent (1 VU, tanpa tekanan).
> Hasil ini menjadi **angka referensi** untuk membandingkan skenario 03, 05, dan 06.

### Latency per Intent (1 VU)

| Intent | avg | p95 | Kestabilan |
|---|---|---|---|
{row("Chitchat", d["baseline_chitchat_avg"], d["baseline_chitchat_p95"])}
{row("Out of Scope", d["baseline_oos_avg"], d["baseline_oos_p95"])}
{row("RAG Short", d["baseline_rag_short_avg"], d["baseline_rag_short_p95"])}
{row("RAG Medium", d["baseline_rag_medium_avg"], d["baseline_rag_medium_p95"])}

### Angka Referensi yang Disimpan
"""
    if baseline:
        md += f"""
| Key | Nilai |
|---|---|
| chitchat p95 | {fmt_ms(baseline.get("chitchat_p95"))} |
| rag_short p95 | {fmt_ms(baseline.get("rag_short_p95"))} |
| rag_medium p95 | {fmt_ms(baseline.get("rag_medium_p95"))} |
| pipeline p95 | {fmt_ms(baseline.get("pipeline_p95"))} |

> ✅ Angka-angka ini otomatis digunakan sebagai pembanding di skenario 03, 05, dan 06.
> Degradasi dihitung dengan rumus: `rasio = latency_aktual / latency_baseline`
> - Rasio < 1.5x → ✅ Normal
> - Rasio 1.5x–3x → ⚠️ Warning
> - Rasio > 3x → ❌ Breaking point
"""
    return md


def section_sweep(d: dict, baseline: dict) -> str:
    err_pct   = (d["http_req_failed_rate"] or 0) * 100
    p95       = d["http_req_duration_p95"]
    pipeline  = d["rag_pipeline_p95"]
    rps       = d["http_reqs_rate"]
    vus_max   = d["vus_max"] or "?"
    cache_pct = (d["rag_cache_hit_rate"] or 0) * 100

    # Degradasi vs baseline
    base_pipeline = baseline.get("pipeline_p95")
    deg = degradation(pipeline, base_pipeline)
    deg_icon = status_icon(deg or 0, "degradation_ratio") if deg else "⚪"

    err_icon = status_icon(err_pct, "error_rate_pct")

    verdict_lines = []
    if err_pct < 1:
        verdict_lines.append("✅ Error rate dalam batas aman.")
    else:
        verdict_lines.append(f"❌ Error rate {fmt_pct(err_pct)} — server mulai drop request. Breaking point kemungkinan terlampaui.")

    if deg:
        if deg < 1.5:
            verdict_lines.append(f"✅ Degradasi latency {deg:.1f}x dari baseline — server masih sehat.")
        elif deg < 3.0:
            verdict_lines.append(f"⚠️ Degradasi latency {deg:.1f}x dari baseline — mendekati batas kapasitas.")
        else:
            verdict_lines.append(f"❌ Degradasi latency {deg:.1f}x dari baseline — breaking point terlampaui.")

    md = f"""
## 🔴 Skenario 03 — Concurrency Sweep

> **Tujuan:** Temukan kapasitas maksimal dan breaking point server.
> **Hubungan dengan Skenario 02:** Degradasi dihitung relatif terhadap baseline skenario 02.

### Hasil Utama

| Metrik | Nilai | Status |
|---|---|---|
| Max VUs | {vus_max} | — |
| Throughput (RPS) | {f"{rps:.2f}" if rps else "N/A"} | — |
| p95 Latency | {fmt_ms(p95)} | — |
| Pipeline p95 | {fmt_ms(pipeline)} | {deg_icon} |
| Error Rate | {fmt_pct(err_pct)} | {err_icon} |
| Cache Hit Rate | {fmt_pct(cache_pct)} | — |

### Degradasi vs Baseline Skenario 02

| Metrik | Baseline (S02) | Aktual (S03) | Rasio | Status |
|---|---|---|---|---|
| Pipeline p95 | {fmt_ms(base_pipeline)} | {fmt_ms(pipeline)} | {f"{deg:.1f}x" if deg else "N/A"} | {deg_icon} |

### Verdict
{"  ".join(verdict_lines)}

> 💡 **Cara baca degradasi:**
> Rasio 1.0x = sama persis dengan baseline. Rasio 3.0x = 3 kali lebih lambat dari kondisi 1 user.
> Breaking point = step VU pertama di mana rasio melewati 3x atau error rate > 1%.

> ⚠️ **Untuk hasil lebih presisi:** Lihat Grafana dashboard k6 (ID: 2587) dan overlay
> panel VUs dengan p95 latency — titik di mana kurva "patah" ke atas adalah breaking point tepat.
"""
    return md


def section_ttft(d: dict) -> str:
    ttft_p95     = d["rag_ttft_p95"]
    ttft_avg     = d["rag_ttft_avg"]
    success_rate = (d["stream_success_rate"] or 0) * 100
    stream_p95   = d["stream_total_p95"]

    ttft_icon    = status_icon(ttft_p95 or 9999, "ttft_p95_ms")
    success_icon = status_icon(success_rate, "stream_success_rate_pct", invert=True)

    # UX rating
    def ux_rating(ms):
        if ms is None: return "N/A"
        if ms < 300:   return "⭐⭐⭐⭐⭐ Excellent"
        if ms < 1000:  return "⭐⭐⭐⭐ Good"
        if ms < 3000:  return "⭐⭐⭐ Acceptable"
        if ms < 5000:  return "⭐⭐ Poor"
        return "⭐ Unacceptable"

    generation_time = None
    if stream_p95 and ttft_p95:
        generation_time = stream_p95 - ttft_p95

    md = f"""
## 🟢 Skenario 04 — Stream TTFT

> **Tujuan:** Ukur kecepatan respons yang dirasakan user saat streaming chatbot.
> **TTFT (Time to First Token)** = waktu dari request dikirim sampai karakter pertama muncul di layar.

### Hasil Utama

| Metrik | Nilai | Status |
|---|---|---|
| TTFT avg | {fmt_ms(ttft_avg)} | — |
| TTFT p95 | {fmt_ms(ttft_p95)} | {ttft_icon} |
| Stream Success Rate | {fmt_pct(success_rate)} | {success_icon} |
| Total Stream Duration p95 | {fmt_ms(stream_p95)} | — |
| Estimated Generation Time | {fmt_ms(generation_time)} | — |

### UX Rating
**TTFT p95:** {ux_rating(ttft_p95)}

> UX Rating berdasarkan standar industri chatbot:
> - < 300ms: User tidak sadar ada jeda
> - 300ms–1s: Jeda tidak mengganggu
> - 1–3s: User melihat loading sebentar
> - 3–5s: User mulai tidak nyaman
> - > 5s: Mayoritas user akan abandon

### Verdict
{"✅ Stream TTFT dalam batas acceptable untuk production." if (ttft_p95 or 9999) < 3000 else "❌ TTFT terlalu tinggi — user akan merasakan lag yang signifikan. Perlu optimasi vLLM atau VRAM."}
{"  ✅ Stream success rate baik." if success_rate >= 95 else f"  ⚠️ Stream success rate {fmt_pct(success_rate)} — ada stream yang putus sebelum selesai."}
"""
    return md


def section_spike(d: dict, baseline: dict) -> str:
    err_pct   = (d["http_req_failed_rate"] or 0) * 100
    p95       = d["http_req_duration_p95"]
    pipeline  = d["rag_pipeline_p95"]
    vus_max   = d["vus_max"] or "?"
    base_p95  = baseline.get("pipeline_p95")
    deg       = degradation(pipeline, base_p95)
    err_icon  = status_icon(err_pct, "error_rate_pct")
    deg_icon  = status_icon(deg or 0, "degradation_ratio") if deg else "⚪"

    resilience = "✅ Resilient" if err_pct < 5 else \
                 "⚠️ Terguncang" if err_pct < 15 else \
                 "❌ Kewalahan"

    md = f"""
## 🟠 Skenario 05 — Spike Test

> **Tujuan:** Simulasi lonjakan traffic tiba-tiba (misal: pengumuman UNHAS viral).
> **Hubungan dengan Skenario 02:** Degradasi post-spike dibandingkan dengan baseline normal.

### Hasil Utama

| Metrik | Nilai | Status |
|---|---|---|
| Max VUs saat Spike | {vus_max} | — |
| Error Rate | {fmt_pct(err_pct)} | {err_icon} |
| p95 Latency (keseluruhan) | {fmt_ms(p95)} | — |
| Pipeline p95 | {fmt_ms(pipeline)} | {deg_icon} |
| Resilience Rating | {resilience} | — |

### Degradasi vs Baseline Skenario 02

| Metrik | Baseline (S02) | Aktual (S05) | Rasio | Status |
|---|---|---|---|---|
| Pipeline p95 | {fmt_ms(base_p95)} | {fmt_ms(pipeline)} | {f"{deg:.1f}x" if deg else "N/A"} | {deg_icon} |

### Verdict
{"✅ Server terbukti resilient terhadap spike traffic." if err_pct < 5 else "⚠️ Server terguncang saat spike — pertimbangkan rate limiting atau request queue di layer BE." if err_pct < 15 else "❌ Server collapse saat spike — perlu circuit breaker dan horizontal scaling sebelum production."}

> 💡 **Untuk melihat recovery time secara presisi:**
> Buka Grafana dashboard k6 → filter time range saat spike selesai → amati berapa lama
> p95 latency dan error rate kembali ke angka baseline skenario 02.
"""
    return md


def section_soak(d: dict, baseline: dict) -> str:
    err_pct   = (d["http_req_failed_rate"] or 0) * 100
    pipeline  = d["rag_pipeline_p95"]
    cache_pct = (d["rag_cache_hit_rate"] or 0) * 100
    base_p95  = baseline.get("pipeline_p95")
    deg       = degradation(pipeline, base_p95)
    err_icon  = status_icon(err_pct, "error_rate_pct")
    deg_icon  = status_icon(deg or 0, "degradation_ratio") if deg else "⚪"

    md = f"""
## 🟣 Skenario 06 — Soak Test

> **Tujuan:** Deteksi memory leak, connection leak, dan degradasi performa jangka panjang.
> **Hubungan dengan Skenario 02:** Degradasi di akhir soak (menit ke-40) dibandingkan baseline.
> Jika degradasi terus naik selama soak = tanda memory leak aktif.

### Hasil Utama

| Metrik | Nilai | Status |
|---|---|---|
| Error Rate (keseluruhan) | {fmt_pct(err_pct)} | {err_icon} |
| Pipeline p95 (akhir soak) | {fmt_ms(pipeline)} | {deg_icon} |
| Cache Hit Rate | {fmt_pct(cache_pct)} | — |

### Degradasi vs Baseline Skenario 02

| Metrik | Baseline (S02) | Akhir Soak (S06) | Rasio | Status |
|---|---|---|---|---|
| Pipeline p95 | {fmt_ms(base_p95)} | {fmt_ms(pipeline)} | {f"{deg:.1f}x" if deg else "N/A"} | {deg_icon} |

### Interpretasi Degradasi Soak

{f"✅ Rasio {deg:.1f}x — Performa stabil selama soak. Tidak ada indikasi memory leak dari sisi latency." if deg and deg < 1.5 else ""}
{f"⚠️ Rasio {deg:.1f}x — Degradasi moderat. Konfirmasi dengan melihat tren RAM di Node Exporter Grafana." if deg and 1.5 <= deg < 3.0 else ""}
{f"❌ Rasio {deg:.1f}x — Degradasi signifikan. Kemungkinan besar ada memory leak di pipeline. Periksa RAM container di cAdvisor Grafana." if deg and deg >= 3.0 else ""}

> 💡 **Ingat:** Angka k6 di sini adalah rata-rata seluruh 40 menit.
> Untuk deteksi memory leak yang akurat, WAJIB lihat **tren RAM** di Node Exporter Grafana
> (apakah RAM naik terus atau flat). Angka ini hanya indikasi awal.

> 🔍 **Jika cache hit rate turun di tengah soak:**
> Redis mulai evict keys karena memory penuh. Set `maxmemory-policy allkeys-lru` di Redis config.
"""
    return md


# ──────────────────────────────────────────────────────
# Final Report Assembly
# ──────────────────────────────────────────────────────
def build_report(sections: list, baseline: dict, generated_at: str) -> str:
    header = f"""# 📊 Load Test Report — RAG Chatbot Akademik UNHAS
**Generated:** {generated_at}
**Environment:** {os.environ.get("RAG_URL", "N/A")}

---

## 🗺️ Panduan Membaca Laporan Ini

Laporan ini dihasilkan otomatis dari output k6 setelah semua skenario selesai.

**Status Icons:**
- ✅ **Hijau** — Aman, performa sesuai ekspektasi
- ⚠️ **Kuning** — Perlu perhatian, belum kritis
- ❌ **Merah** — Kritis, perlu tindakan sebelum production

**Hubungan Antar Skenario:**
Skenario 02 (Baseline) menghasilkan angka referensi performa 1 user tanpa tekanan.
Skenario 03, 05, dan 06 membandingkan hasil mereka terhadap angka ini menggunakan
**rasio degradasi**: `aktual / baseline`. Rasio ideal < 1.5x, batas > 3x = breaking point.

---

"""
    footer = f"""
---

## 📋 Summary Tabel — Semua Skenario

| Skenario | Error Rate | p95 Latency | Degradasi vs Baseline | Status |
|---|---|---|---|---|
"""

    return header + "\n".join(sections) + footer


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RAG Load Test Summarizer")
    parser.add_argument("--scenario", required=True,
                        choices=["01","02","03","04","05","06"],
                        help="Nomor skenario")
    parser.add_argument("--input", required=True,
                        help="Path ke k6 summary JSON (--summary-export output)")
    parser.add_argument("--report", default=REPORT_FILE,
                        help="Path output laporan Markdown")
    args = parser.parse_args()

    os.makedirs("reports", exist_ok=True)
    os.makedirs("summarizer", exist_ok=True)

    data     = parse_k6_summary(args.input)
    baseline = load_baseline()
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Generate section
    if args.scenario == "01":
        section = section_smoke(data)
    elif args.scenario == "02":
        baseline = save_baseline(data)  # simpan baseline setelah S02
        section  = section_baseline(data, baseline)
    elif args.scenario == "03":
        section = section_sweep(data, baseline)
    elif args.scenario == "04":
        section = section_ttft(data)
    elif args.scenario == "05":
        section = section_spike(data, baseline)
    elif args.scenario == "06":
        section = section_soak(data, baseline)

    # Append ke report file (gabungan)
    report_path = args.report
    if not Path(report_path).exists():
        with open(report_path, "w") as f:
            f.write(f"# 📊 Load Test Report — RAG Chatbot Akademik UNHAS\n")
            f.write(f"**Generated:** {now}\n")
            f.write(f"**Target:** {os.environ.get('RAG_URL', 'N/A')}\n\n")
            f.write("---\n\n")
            f.write("## 🗺️ Panduan Membaca Laporan\n\n")
            f.write("- ✅ Hijau = Aman\n- ⚠️ Kuning = Perlu perhatian\n- ❌ Merah = Kritis\n\n")
            f.write("**Degradasi** dihitung relatif terhadap Skenario 02 (Baseline 1 VU).\n")
            f.write("Rasio < 1.5x ✅ | 1.5x–3x ⚠️ | > 3x ❌\n\n---\n\n")

    with open(report_path, "a") as f:
        f.write(section)
        f.write("\n---\n\n")

    print(f"[summarizer] ✅ Section S{args.scenario} ditambahkan ke: {report_path}")


if __name__ == "__main__":
    main()