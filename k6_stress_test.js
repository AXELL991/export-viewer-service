import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '10s', target: 100 },
    { duration: '20s', target: 100 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
};

const BASE_URL = 'http://export-viewer-service:8000';
const INTERNAL_TOKEN = 'c2db8b6b0449ceb6cfb3252e060999e5d220e239eadebdde70af7e3885c13e08';

const pdf = open('/pdfs/stress_9mb.pdf', 'b');

export default function () {
  const res = http.post(`${BASE_URL}/v1/documents/upload`, {
    file: http.file(pdf, 'sample.pdf', 'application/pdf'),
  }, {
    headers: {
      'X-Internal-Token': INTERNAL_TOKEN,
    },
  });

  check(res, {
    'status is 201': (r) => r.status === 201,
    'has sha256': (r) => !!r.json().sha256,
  });

  sleep(1);
}
