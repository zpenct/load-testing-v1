// SKENARIO 4: Streaming TTFT (Time to First Token)
// Tujuan: Ukur perceived responsiveness chatbot dari sisi user
// Endpoint: /api/query/stream (SSE)
// TTFT = waktu dari request dikirim sampai chunk pertama diterima

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { ttftMs, errorRate } from './utils/metrics.js';
import { getRAGOnlyPrompt } from './utils/prompts.js';

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';
const headers  = { 'Content-Type': 'application/json' };

// Ukur total stream duration (TTFT sampai event meta terakhir)
const streamTotalMs = new Trend('stream_total_duration_ms', true);
const streamSuccess = new Rate('stream_success_rate');

export const options = {
  stages: [
    { duration: '2m', target: 1  },   // baseline TTFT
    { duration: '3m', target: 5  },   // 5 concurrent streaming sessions
    { duration: '3m', target: 10 },   // 10 concurrent
    { duration: '3m', target: 15 },   // medium concurrent streaming
    { duration: '2m', target: 0  },   // ramp down
  ],
  thresholds: {
    rag_ttft_ms:          ['p(95)<3000'],  // TTFT < 3 detik untuk 95% request
    stream_total_duration_ms: ['p(90)<60000'],
    stream_success_rate:  ['rate>0.90'],
  },
};

export default function () {
  const startTime = Date.now();
  let firstTokenReceived = false;
  let firstTokenTime = 0;
  let totalTokens = 0;
  let gotMeta = false;

  const res = http.post(
    `${BASE_URL}/api/query/stream`,
    JSON.stringify({
      question: getRAGOnlyPrompt(),
      history: [],
      role: "public",
    }),
    {
      headers,
      timeout: '120s',
      responseType: 'text',
    }
  );

  // Parse SSE response (k6 baca seluruh stream sebelum return)
  if (res.status === 200 && res.body) {
    const lines = res.body.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'token' && !firstTokenReceived) {
            firstTokenReceived = true;
            firstTokenTime = Date.now() - startTime;
            ttftMs.add(firstTokenTime);
          }
          if (event.type === 'token') {
            totalTokens++;
          }
          if (event.type === 'meta') {
            gotMeta = true;
          }
        } catch {}
      }
    }
  }

  const totalDuration = Date.now() - startTime;
  streamTotalMs.add(totalDuration);
  streamSuccess.add(res.status === 200 && firstTokenReceived && gotMeta);
  errorRate.add(res.status !== 200);

  check(res, {
    'stream status 200':      (r) => r.status === 200,
    'got first token':        () => firstTokenReceived,
    'got meta event':         () => gotMeta,
    'TTFT < 3s':              () => firstTokenTime < 3000,
  });

  sleep(Math.random() * 2 + 1);
}