// SKENARIO 1: Smoke Test
// Tujuan: Validasi endpoint hidup, baseline latency 1 user
// Target: /api/query dan /api/query/stream

import http from 'k6/http';
import { check, sleep } from 'k6';
import { recordMetrics, errorRate } from './utils/metrics.js';

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';

export const options = {
  vus: 1,
  duration: '2m',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<10000'],  // LLM bisa lambat, toleransi 10s
  },
};

const headers = { 'Content-Type': 'application/json' };

export default function () {
  // Test non-streaming
  const resQuery = http.post(
    `${BASE_URL}/api/query`,
    JSON.stringify({
      question: "apa syarat wisuda di UNHAS?",
      history: [],
      role: "public",
    }),
    { headers, timeout: '60s' }
  );

  check(resQuery, {
    '[query] status 200': (r) => r.status === 200,
    '[query] has answer': (r) => {
      try { return JSON.parse(r.body).answer !== undefined; }
      catch { return false; }
    },
    '[query] has debug': (r) => {
      try { return JSON.parse(r.body).debug !== undefined; }
      catch { return false; }
    },
  });
  recordMetrics(resQuery.body);
  errorRate.add(resQuery.status !== 200);

  sleep(2);

  // Test health endpoint sebagai sanity check
  const resHealth = http.get(`${BASE_URL}/api/health`, { timeout: '10s' });
  check(resHealth, {
    '[health] status 200': (r) => r.status === 200,
  });

  sleep(3);
}