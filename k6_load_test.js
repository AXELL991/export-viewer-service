import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

export let options = {
  stages: [
    { duration: '10s', target: 100 }, // spike 100 VUs
    { duration: '20s', target: 100 }, // sustain
    { duration: '10s', target: 0 },   // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% < 2s
    http_req_failed: ['rate<0.01'], // <1% failures
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(95)', 'p(99)'],
};

const BASE_URL = __ENV.BASE_URL || 'http://universidad.localhost';
const PDF_PATH = __ENV.PDF_PATH || 'sample.pdf'; // path on k6 runner

export default function () {
  const pdf = open(PDF_PATH, 'b');
  const data = {
    file: http.file(pdf, 'sample.pdf', 'application/pdf'),
  };
  const res = http.post(`${BASE_URL}/process`, data);

  check(res, {
    'status is 201': (r) => r.status === 201,
    'has sha256': (r) => !!r.json().sha256,
  });

  sleep(1);
}

