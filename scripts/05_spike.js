// SKENARIO 5: Spike Test
// Tujuan: Simulasi lonjakan traffic tiba-tiba (misal: pengumuman UNHAS viral)
// Pattern: traffic normal → spike mendadak → balik normal → spike lagi

import http from 'k6/http';
import { check, sleep } from 'k6';
import { recordMetrics, errorRate } from './utils/metrics.js';
import { getRandomPrompt } from './utils/prompts.js';

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';
const headers  = { 'Content-Type': 'application/json' };

export const options = {
  stages: [
    { duration: '2m',  target: 5  },   // traffic normal
    // { duration: '30s', target: 50 },   // SPIKE! lonjakan tiba-tiba
    // { duration: '2m',  target: 50 },   // tahan spike
    // { duration: '1m',  target: 5  },   // balik ke normal
    // { duration: '2m',  target: 5  },   // recovery observation
    // { duration: '30s', target: 40 },   // spike kedua (lebih kecil)
    // { duration: '1m',  target: 40 },   // tahan
    // { duration: '2m',  target: 0  },   // ramp down final
  ],
  thresholds: {
    http_req_failed:  ['rate<0.30'],   // toleransi lebih tinggi saat spike
    rag_error_rate:   ['rate<0.30'],
    http_req_duration: ['p(95)<60000'],
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
    'not 500':    (r) => r.status !== 500,
    'not crash':  (r) => r.status !== 0,
  });

  errorRate.add(res.status !== 200);
  recordMetrics(res.body);
  sleep(1);
}