import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 1,
  iterations: 1,
};

const BASE_URL = 'http://export-viewer-service:8000';
const INTERNAL_TOKEN = 'c2db8b6b0449ceb6cfb3252e060999e5d220e239eadebdde70af7e3885c13e08';

const pdf = open('/pdfs/stress_9mb.pdf', 'b');

export default function () {
  const res = http.post(`${BASE_URL}/v1/documents/upload`, {
    file: http.file(pdf, 'test.pdf', 'application/pdf'),
  }, {
    headers: {
      'X-Internal-Token': INTERNAL_TOKEN,
    },
  });

  check(res, {
    'status is 201': (r) => r.status === 201,
  });

  console.log(`PDF 9MB: status=${res.status} duration=${res.timings.duration}ms`);
}
