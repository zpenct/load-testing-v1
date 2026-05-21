// SKENARIO 2: Baseline per Intent
// Tujuan: Ukur latency breakdown per tipe intent (rag vs chitchat vs OOS)
// Penting: jalankan ini SEBELUM skenario berat, sebagai baseline reference

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend } from 'k6/metrics';
import { recordMetrics, errorRate } from './utils/metrics.js';
import {
  PROMPTS_CHITCHAT,
  PROMPTS_RAG_SHORT_BASE,
  PROMPTS_RAG_MEDIUM_BASE,
  PROMPTS_OUT_OF_SCOPE,
} from "./utils/prompts.js";

const BASE_URL = __ENV.RAG_URL || 'http://localhost:8000';
const headers  = { 'Content-Type': 'application/json' };

// Trend terpisah per intent
const latencyRAGShort  = new Trend('baseline_latency_rag_short_ms', true);
const latencyRAGMedium = new Trend('baseline_latency_rag_medium_ms', true);
const latencyChitchat  = new Trend('baseline_latency_chitchat_ms', true);
const latencyOOS       = new Trend('baseline_latency_oos_ms', true);

export const options = {
  vus: 1,
  iterations: 20,  // 5 iterasi × 4 grup intent
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'baseline_latency_chitchat_ms': ['p(95)<3000'],
    'baseline_latency_rag_short_ms': ['p(95)<15000'],
  },
};

function queryOnce(question) {
  return http.post(
    `${BASE_URL}/api/query`,
    JSON.stringify({ question, history: [], role: "public" }),
    { headers, timeout: '120s' }
  );
}

export default function () {
  group('RAG Short', () => {
    const q = PROMPTS_RAG_SHORT[Math.floor(Math.random() * PROMPTS_RAG_SHORT.length)];
    const res = queryOnce(q);
    check(res, { 'status 200': (r) => r.status === 200 });
    latencyRAGShort.add(res.timings.duration);
    recordMetrics(res.body);
    sleep(2);
  });

  group('RAG Medium', () => {
    const q = PROMPTS_RAG_MEDIUM[Math.floor(Math.random() * PROMPTS_RAG_MEDIUM.length)];
    const res = queryOnce(q);
    check(res, { 'status 200': (r) => r.status === 200 });
    latencyRAGMedium.add(res.timings.duration);
    recordMetrics(res.body);
    sleep(2);
  });

  group('Chitchat', () => {
    const q = PROMPTS_CHITCHAT[Math.floor(Math.random() * PROMPTS_CHITCHAT.length)];
    const res = queryOnce(q);
    check(res, { 'status 200': (r) => r.status === 200 });
    latencyChitchat.add(res.timings.duration);
    recordMetrics(res.body);
    sleep(1);
  });

  group('Out of Scope', () => {
    const q = PROMPTS_OUT_OF_SCOPE[Math.floor(Math.random() * PROMPTS_OUT_OF_SCOPE.length)];
    const res = queryOnce(q);
    check(res, { 'status 200': (r) => r.status === 200 });
    latencyOOS.add(res.timings.duration);
    recordMetrics(res.body);
    sleep(1);
  });
}