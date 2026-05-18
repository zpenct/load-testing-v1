// SKENARIO 3: Concurrency Sweep — INI skenario paling penting
// Tujuan: Temukan titik saturasi GPU L40S
// Method: step naik perlahan, amati degradasi latency & error rate
// L40S 48GB VRAM → prediksi saturasi di sekitar 20-30 concurrent users

import http from 'k6/http';
import { check, sleep } from 'k6';
import { recordMetrics, errorRate, pipelineTotalTime } from './utils/metrics.js';
import { getRandomPrompt } from './utils/prompts.js';

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';
const headers  = { 'Content-Type': 'application/json' };

export const options = {
  stages: [
    { duration: '2m',  target: 1  },  // baseline warmup
    { duration: '3m',  target: 5  },  // normal low traffic
    // { duration: '3m',  target: 10 },  // moderate
    // { duration: '3m',  target: 15 },  // medium load
    // { duration: '3m',  target: 20 },  // expected comfortable max
    // { duration: '3m',  target: 25 },  // mulai masuk danger zone
    // { duration: '3m',  target: 30 },  // stress
    // { duration: '3m',  target: 35 },  // beyond expected capacity
    // { duration: '3m',  target: 40 },  // extreme — amati apakah crash/OOM
    { duration: '3m',  target: 0  },  // ramp down, cek recovery
  ],
  thresholds: {
    // Threshold WARN saja, jangan fail — kita mau lihat semua data
    http_req_duration:    ['p(90)<30000'],
    http_req_failed:      ['rate<0.20'],
    rag_error_rate:       ['rate<0.20'],
    rag_pipeline_total_time_ms: ['p(90)<25000'],
  },
};

export default function () {
  const res = http.post(
    `${BASE_URL}/api/query`,
    JSON.stringify({
      question: getRandomPrompt(),
      history: [],
      role: "public",
    }),
    { headers, timeout: '120s' }
  );

  check(res, {
    'status 200': (r) => r.status === 200,
    'no 429':     (r) => r.status !== 429,
    'no 500':     (r) => r.status !== 500,
    'no timeout': (r) => r.status !== 0,
  });

  errorRate.add(res.status !== 200);
  recordMetrics(res.body);

  // Realistic think time — mahasiswa baca response sebelum kirim lagi
  sleep(Math.random() * 3 + 2); // 2-5 detik
}