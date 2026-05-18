import { Trend, Rate, Counter } from 'k6/metrics';

// Custom metrics khusus RAG pipeline
export const pipelineTotalTime  = new Trend('rag_pipeline_total_time_ms', true);
export const ragTopScore        = new Trend('rag_retrieval_top_score');
export const ttftMs             = new Trend('rag_ttft_ms', true);
export const cacheHitRate       = new Rate('rag_cache_hit');
export const ragModeCounter     = new Counter('rag_mode_rag');
export const chitchatCounter    = new Counter('rag_mode_chitchat');
export const oosCounter         = new Counter('rag_mode_out_of_scope');
export const blockedCounter     = new Counter('rag_mode_blocked');
export const errorRate          = new Rate('rag_error_rate');

// Parse response body dan record custom metrics
export function recordMetrics(body) {
  if (!body) return;
  try {
    const data = JSON.parse(body);
    if (data.debug) {
      if (data.debug.total_time_s) {
        pipelineTotalTime.add(data.debug.total_time_s * 1000);
      }
      if (data.debug.top_score) {
        ragTopScore.add(data.debug.top_score);
      }
      // Track intent distribution
      switch (data.debug.mode) {
        case 'rag':           ragModeCounter.add(1);     break;
        case 'chitchat':      chitchatCounter.add(1);    break;
        case 'out_of_scope':  oosCounter.add(1);         break;
        case 'blocked':
        case 'blocked_moderation': blockedCounter.add(1); break;
        case 'cache_hit':     cacheHitRate.add(1);       break;
      }
      if (data.debug.mode !== 'cache_hit') {
        cacheHitRate.add(0);
      }
    }
  } catch (e) {
    // silently fail — body mungkin stream atau non-JSON
  }
}