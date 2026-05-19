Here is the fully translated and polished English version of your README:

***

# K6 Grafana Monitoring — UNHAS Academic RAG Chatbot

A complete load testing stack for measuring the performance of the Universitas Hasanuddin (UNHAS) Academic RAG Chatbot endpoints. Built on **k6** as the load generator, with **InfluxDB + Grafana** for real-time visualization, and **Prometheus + Node Exporter + cAdvisor** for infrastructure monitoring.

The primary goal of this stack is to help the team find breaking points, validate long-term stability, and generate structured reports ready for analysis, both manually and with AI assistance.

***

## Table of Contents

- [Stack Architecture](#stack-architecture)
- [Folder Structure](#folder-structure)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Usage](#usage)
- [Load Test Scenarios](#load-test-scenarios)
- [Generated Output](#generated-output)
- [Real-time Monitoring](#real-time-monitoring)
- [Warning Signs — Quick Reference](#warning-signs--quick-reference)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Dependency Versions](#dependency-versions)

***

## Stack Architecture

```
┌─────────────┐     HTTP      ┌──────────────────────┐
│   k6 Runner │ ────────────► │  RAG Server / Mock   │
└──────┬──────┘               └──────────────────────┘
       │ metrics (InfluxDB line protocol)
       ▼
┌─────────────┐     query     ┌──────────────────────┐
│  InfluxDB   │ ◄──────────── │       Grafana        │
└─────────────┘               └──────────────────────┘
                                        ▲
┌─────────────┐     scrape             │
│ Prometheus  │ ─────────────────────► │
└──────┬──────┘
       │ scrape
       ├── Node Exporter  (host CPU, RAM, disk)
       └── cAdvisor       (per-container metrics)
```

All monitoring components (InfluxDB, Grafana, Prometheus, Node Exporter, cAdvisor) run as Docker containers managed through a single `docker-compose.monitoring.yml` file. k6 runs on the host and sends metrics directly to InfluxDB.

***

## Prerequisites

### Software

| Software | Minimum Version | Notes |
|---|---|---|
| k6 | v0.50+ | Load testing engine |
| Docker | v24+ | Runs the monitoring stack |
| Docker Compose | v2.20+ | Container orchestration |
| Python | v3.9+ | Summarizer & store_raw scripts |

### Install k6

Use the binary method — more reliable than `apt` on most distributions:

```bash
wget -qO k6.tar.gz https://github.com/grafana/k6/releases/download/v0.55.0/k6-v0.55.0-linux-amd64.tar.gz
tar xf k6.tar.gz
sudo mv k6-v0.55.0-linux-amd64/k6 /usr/local/bin/
rm -rf k6-v0.55.0-linux-amd64 k6.tar.gz

k6 version  # verify installation
```

***

## Configuration

### Environment Files

There are two `.env` files — both are consumed exclusively by the k6 runner, not by the RAG server itself.

`.env.test` — targets the local mock server:
```env
RAG_URL=http://localhost:8000
INFLUX_URL=http://localhost:8086/k6
```

`.env.poc` — targets the L40S POC server:
```env
RAG_URL=http://<L40S-IP>:8000
INFLUX_URL=http://localhost:8086/k6
```

> **Note:** `RATE_LIMIT_TEXT_PER_MINUTE` is configured on the RAG server side (`rag-prototype/.env`), not here. For heavy-load scenarios (03, 05, 06), set this value to `9999` on the RAG server to prevent the rate limiter from interfering with test results.

***

## Usage

### Step 1 — Create Required Directories

```bash
mkdir -p grafana/provisioning/datasources
mkdir -p grafana/provisioning/dashboards
mkdir -p grafana/dashboards
mkdir -p prometheus reports/raw summarizer tmp
```

### Step 2 — Start the Monitoring Stack

```bash
docker compose -f docker-compose.monitoring.yml up -d
docker compose -f docker-compose.monitoring.yml ps
```

All five containers must show a `running` status:

```
rag_influxdb       :8086
rag_grafana        :3001
rag_prometheus     :9090
rag_node_exporter  :9100
rag_cadvisor       :8080
```

### Step 3 — Verify Prometheus Targets

Open `http://localhost:9090/targets` — all targets must show status **UP**:
- `node-exporter:9100`
- `cadvisor:8080`

### Step 4 — Import Grafana Dashboards

Open `http://localhost:3001` (login: `admin` / `admin`), then import the following dashboards:

**Dashboards → New → Import → enter ID → Load → select datasource → Import**

| ID | Datasource | Dashboard Name | Used In |
|---|---|---|---|
| 2587 | InfluxDB-k6 | k6 Load Testing Results | All scenarios |
| 1860 | Prometheus | Node Exporter Full | 03, 05, 06 |
| 14282 | Prometheus | cAdvisor | 03, 06 |

> If you see *"No data sources of type Prometheus found"* during import, run `docker restart rag_grafana`, wait 10 seconds, then try again.

### Step 5 — Prepare the Target

**Option A — Mock server** (for validating scripts without the real RAG server):
```bash
# Run in a separate terminal
uvicorn mock.main:app --host 0.0.0.0 --port 8000 --reload
```

**Option B — Real RAG server** (for actual benchmarking):
```bash
# In the rag-prototype repo, edit .env:
# RATE_LIMIT_TEXT_PER_MINUTE=9999
# Then start the RAG server as usual
```

### Step 6 — Run the Load Tests

**All scenarios at once (recommended):**
```bash
chmod +x run_all.sh

./run_all.sh --env .env.test   # mock server
./run_all.sh --env .env.poc    # POC server
```

**A single specific scenario:**
```bash
export $(cat .env.test | xargs)

k6 run \
  --out influxdb=$INFLUX_URL \
  --env RAG_URL=$RAG_URL \
  --tag testid=sweep_manual \
  scripts/03_concurrency_sweep.js
```

***

## Load Test Scenarios

Six scenarios are designed to answer different questions about system performance. Run them in order — Scenario 02 **must** be run before 03, 05, and 06, as it generates `baseline.json` used as the comparison reference.

### Scenario 01 — Smoke Test

| | |
|---|---|
| **File** | `01_smoke.js` |
| **VU Pattern** | 1 VU constant |
| **Duration** | ~2 minutes |

**Purpose:** Confirms the endpoint is alive and responding correctly before any heavy testing begins. This scenario does not measure performance — it only validates that all components (k6, server, InfluxDB, Grafana) are properly connected.

**When to run:** Always run first, especially after re-deployment or server configuration changes.

**Monitored metrics:** HTTP status codes, basic response time, zero errors.

***

### Scenario 02 — Baseline per Intent

| | |
|---|---|
| **File** | `02_baseline_intent.js` |
| **VU Pattern** | 1 VU, 20 iterations |
| **Duration** | ~5 minutes |

**Purpose:** Measures endpoint latency under zero-concurrency conditions. Results are saved as `summarizer/baseline.json` and referenced by scenarios 03, 05, and 06 to calculate degradation ratios.

**Why it matters:** Without a baseline, there is no reference point to determine whether latency degradation under heavy load is significant or within acceptable tolerance.

**Output:** `summarizer/baseline.json` containing p50, p95, p99, and mean latency per intent.

**Monitored metrics:** Latency per intent (schedule, curriculum, fees, general info, chitchat).

***

### Scenario 03 — Concurrency Sweep

| | |
|---|---|
| **File** | `03_concurrency_sweep.js` |
| **VU Pattern** | 1 → 5 → 10 → 15 → 20 → 25 → 30 → 35 → 40 (stepped, 3 min each) |
| **Duration** | ~28 minutes |

**Purpose:** Finds the **breaking point** — the VU level where latency spikes disproportionately or error rate exceeds 1%. This is the most informative scenario for determining maximum server capacity.

**How to read results:** Look for the VU step where p95 latency suddenly jumps more than 2× compared to the previous step. That is the breaking point. Below that threshold is the safe throughput zone.

**Configurable options:**
```javascript
// scripts/03_concurrency_sweep.js
export const options = {
  stages: [
    { duration: '2m', target: 1  },
    { duration: '3m', target: 5  },
    { duration: '3m', target: 10 },
    // ... add higher steps for L40S server
    { duration: '3m', target: 60 }, // example for more powerful GPU
  ],
};
```

**Monitored metrics:** p95 latency per VU step, error rate, CPU (Node Exporter), RAM, container resources (cAdvisor).

**Open dashboards:** k6 (2587) + Node Exporter (1860) + cAdvisor (14282)

***

### Scenario 04 — Stream TTFT

| | |
|---|---|
| **File** | `04_stream_ttft.js` |
| **VU Pattern** | 1 → 5 → 10 → 15 |
| **Duration** | ~13 minutes |

**Purpose:** Measures **Time to First Token (TTFT)** — the time from when a request is sent until the first byte of the response is received. This is the most important UX metric for streaming endpoints, as users perceive chatbot responsiveness from how quickly the first token appears, not how long the full response takes.

**Threshold:** TTFT p95 above **3 seconds** is considered unacceptable for streaming UX.

**Monitored metrics:** TTFT p50/p95/p99, stream success rate (percentage of streams that complete without disconnecting).

**Open dashboards:** k6 (2587)

***

### Scenario 05 — Spike Test

| | |
|---|---|
| **File** | `05_spike.js` |
| **VU Pattern** | 5 → spike 50 → 5 → spike 40 |
| **Duration** | ~10 minutes |

**Purpose:** Tests system resilience against sudden, unpredictable traffic surges — for example, when new student admission announcements or exam schedules are released and hundreds of students access the chatbot simultaneously within a short window.

**How to read results:** Check whether error rate spikes during the surge, and how quickly the system recovers to normal after the spike ends. Slow recovery time indicates issues with queue management or memory handling.

**Monitored metrics:** Error rate during spike, latency recovery time, p99 latency at peak spike.

**Open dashboards:** k6 (2587) + Node Exporter (1860)

***

### Scenario 06 — Soak Test

| | |
|---|---|
| **File** | `06_soak.js` |
| **VU Pattern** | 10 VUs constant |
| **Duration** | ~45 minutes |

**Purpose:** Detects problems that only surface after the server has been running for an extended period: memory leaks, cache degradation, unreleased database connections, or gradual performance decline. Moderate load with long duration.

**How to read results:** If latency at minute 40 is consistently higher than at minute 5 despite constant VU count, there is gradual degradation. If RAM continuously rises without plateauing, a memory leak is likely present.

**Monitored metrics:** Latency trend over time (not peak), RAM usage (Node Exporter), cache hit rate, stream success rate.

**Open dashboards:** k6 (2587) + Node Exporter (1860) + cAdvisor (14282)

***

### Scenario Summary

| # | Scenario | Duration | Question Answered |
|---|---|---|---|
| 01 | Smoke Test | ~2 min | Is the endpoint alive? |
| 02 | Baseline Intent | ~5 min | What is latency under zero load? |
| 03 | Concurrency Sweep | ~28 min | At what VU count does the server break? |
| 04 | Stream TTFT | ~13 min | How responsive is the streaming UX? |
| 05 | Spike Test | ~10 min | Can it handle sudden traffic surges? |
| 06 | Soak Test | ~45 min | Is it stable after extended runtime? |

***

## Generated Output

Each time `run_all.sh` completes, two types of output are automatically generated.

### 1. Combined Markdown Report

```
reports/load_test_report_20260518_090000.md
```

Contains a summary of all scenarios in a single file with per-metric status (✅ / ⚠️ / ❌), degradation ratios vs. the Scenario 02 baseline, and a verdict with interpretation per scenario.

### 2. Raw JSON per Scenario

```
reports/raw/20260518_090000/
├── session_meta.json
├── 01_smoke_test_raw.json
├── 02_baseline_intent_raw.json
├── 03_concurrency_sweep_raw.json
├── 04_stream_ttft_raw.json
├── 05_spike_test_raw.json
└── 06_soak_test_raw.json
```

Each raw file contains:
- **Scenario metadata** — purpose, VU pattern, endpoint, critical metrics
- **Server specifications** — OS, CPU, RAM, GPU (via `nvidia-smi`)
- **Baseline reference** — values from Scenario 02 (Scenarios 03, 05, 06 only)
- **Raw k6 metrics** — all raw metrics output from k6

> Raw files are designed to be pasted directly into external AI tools (ChatGPT, Claude, etc.) for in-depth analysis. Simply copy the file contents along with your analysis question.

***

## Real-time Monitoring

Open Grafana at `http://localhost:3001` while tests are running:

| Scenario | Dashboards |
|---|---|
| 01 Smoke | k6 (2587) |
| 02 Baseline | k6 (2587) |
| 03 Sweep | k6 (2587) + Node Exporter (1860) + cAdvisor (14282) |
| 04 TTFT | k6 (2587) |
| 05 Spike | k6 (2587) + Node Exporter (1860) |
| 06 Soak | k6 (2587) + Node Exporter (1860) + cAdvisor (14282) |

> **Tip:** Set the Grafana time range to **Last 5 minutes** while tests are running to keep graphs responsive and uncluttered.

***

## Warning Signs — Quick Reference

| Signal | Critical Value | Meaning |
|---|---|---|
| Error rate | > 1% | Server is dropping requests |
| p95 latency | Jumps > 2× in a single VU step | Breaking point reached |
| TTFT p95 | > 3 seconds | Streaming UX is unacceptable |
| Degradation vs baseline | > 3× | Load far exceeds safe capacity |
| Sustained CPU | > 85% | CPU bottleneck |
| RAM continuously rising | No plateau | Active memory leak |
| Cache hit rate dropping | Occurs mid-soak | Redis eviction is active |
| Stream success rate | < 95% | Streams frequently drop before completing |

***

## Customization

### Changing the Target URL

```bash
# Override directly without an env file
./run_all.sh http://10.20.30.40:8000

# Or export manually for a single scenario
export RAG_URL=http://10.20.30.40:8000
export INFLUX_URL=http://localhost:8086/k6
k6 run --out influxdb=$INFLUX_URL --env RAG_URL=$RAG_URL scripts/03_concurrency_sweep.js
```

### Skipping Specific Scenarios

Comment out the lines you don't want to run in `run_all.sh`:

```bash
run_test "01" "01_smoke"             "01_smoke.js"
run_test "02" "02_baseline_intent"   "02_baseline_intent.js"
run_test "03" "03_concurrency_sweep" "03_concurrency_sweep.js"
# run_test "04" "04_stream_ttft"     "04_stream_ttft.js"   ← skip
# run_test "05" "05_spike"           "05_spike.js"         ← skip
run_test "06" "06_soak"              "06_soak.js"
```

> ⚠️ **Do not skip Scenario 02** if you plan to run 03, 05, or 06. Without `baseline.json`, degradation ratios cannot be calculated.

### Changing the Prompt Distribution

Edit `scripts/utils/prompts.js`:

```javascript
export function getRandomPrompt() {
  const rand = Math.random();
  if (rand < 0.30) {         // 30% chitchat
    // ...
  } else if (rand < 0.70) {  // 40% RAG queries
    // ...
  }
  // remaining 30% other intents
}
```

***

## Troubleshooting

### `k6: command not found`

Use the binary method — the k6 apt repository requires GPG setup that frequently fails:

```bash
wget -qO k6.tar.gz https://github.com/grafana/k6/releases/download/v0.55.0/k6-v0.55.0-linux-amd64.tar.gz
tar xf k6.tar.gz
sudo mv k6-v0.55.0-linux-amd64/k6 /usr/local/bin/
```

### Grafana: *"No data sources of type Prometheus found"*

```bash
docker restart rag_grafana
# Wait 10 seconds, then re-import the dashboard
```

### InfluxDB not receiving data from k6

```bash
docker logs rag_influxdb --tail 20
curl http://localhost:8086/query?q=SHOW+DATABASES
# Verify that database 'k6' appears in the output
```

### `baseline.json` contains null values

```bash
# Debug metric structure from k6 output
cat tmp/summary_02_baseline_intent.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for k, v in data.get('metrics', {}).items():
    if 'baseline' in k:
        print(k, list(v.keys()))
"

# Delete and regenerate
rm summarizer/baseline.json
python3 summarizer/summarize.py \
  --scenario 02 \
  --input tmp/summary_02_baseline_intent.json \
  --report reports/test_fix.md
```

### Stopping the Monitoring Stack

```bash
# Stop all containers
docker compose -f docker-compose.monitoring.yml down

# Stop and remove all volumes (Grafana & InfluxDB data will be lost)
docker compose -f docker-compose.monitoring.yml down -v
```

## References

- [k6 Documentation](https://k6.io/docs/)
- [k6 InfluxDB Output](https://grafana.com/docs/k6/latest/results-output/real-time/influxdb/)
- [Grafana Dashboard: k6 Load Testing Results (2587)](https://grafana.com/grafana/dashboards/2587)
- [Grafana Dashboard: Node Exporter Full (1860)](https://grafana.com/grafana/dashboards/1860)
- [Grafana Dashboard: cAdvisor (14282)](https://grafana.com/grafana/dashboards/14282)