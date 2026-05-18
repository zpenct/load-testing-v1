// SKENARIO 6: Soak Test
// Tujuan: Deteksi memory leak VRAM, Redis memory bloat, PostgreSQL connection leak
// Jalankan 10 VUs selama 30-45 menit — amati tren latency (naik = memory leak)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { recordMetrics, errorRate, pipelineTotalTime } from './utils/metrics.js';
import { getRandomPrompt } from './utils/prompts.js';

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';
const headers  = { 'Content-Type': 'application/json' };

export const options = {
  stages: [
    { duration: '3m',  target: 10 },  // ramp up
    { duration: '40m', target: 10 },  // SOAK — amati tren latency dari menit ke menit
    { duration: '2m',  target: 0  },  // ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],
    // Latency tidak boleh naik lebih dari 3x baseline selama soak
    rag_pipeline_total_time_ms: ['p(95)<45000'],
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
    'status 200':  (r) => r.status === 200,
    'no 500':      (r) => r.status !== 500,
  });

  errorRate.add(res.status !== 200);
  recordMetrics(res.body);

  // Think time lebih panjang di soak test — simulasi user natural
  sleep(Math.random() * 5 + 3); // 3-8 detik
}