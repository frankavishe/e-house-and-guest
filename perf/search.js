// Search load test (T145, SC-002): p95 of GET /listings/search must stay under 500 ms with
// 20k listings (backend `python -m app.seed_perf --count 20000`).
//
//   docker run --rm -i -e BASE_URL=http://host.docker.internal:8010 grafana/k6:0.54.0 run - < perf/search.js
//
// Each iteration picks one realistic query: category browse, region, price, text, attribute
// filters and availability periods (nights, days, slots, months, stock), sorted and paged.
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  scenarios: {
    search: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.RATE || 20), // requests per second
      timeUnit: "1s",
      duration: __ENV.DURATION || "60s",
      preAllocatedVUs: 20,
      maxVUs: 60,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

function isoDate(daysAhead) {
  const d = new Date(Date.now() + daysAhead * 86400000);
  return d.toISOString().slice(0, 10);
}

const REGIONS = [2, 7, 1, 11, 18]; // arusha, dar-es-salaam, dodoma, iringa, kagera
const SORTS = ["newest", "price_asc", "price_desc", "rating"];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

function queries() {
  const start = 5 + Math.floor(Math.random() * 50);
  return [
    "",
    "category=accommodation",
    `category=guest-houses&region=${pick(REGIONS)}&start_date=${isoDate(start)}&end_date=${isoDate(start + 2)}`,
    `category=accommodation&attr.max_guests.min=2&start_date=${isoDate(start)}&end_date=${isoDate(start + 3)}`,
    "category=vehicles&attr.vehicle_type=4x4&attr.with_driver=true",
    `category=cars&start_date=${isoDate(start)}&end_date=${isoDate(start + 1)}&price_max=150000`,
    `category=tents&start_date=${isoDate(start)}&end_date=${isoDate(start + 1)}&quantity=3`,
    `category=equipment&region=${pick(REGIONS)}`,
    `category=event-halls&start=${isoDate(start)}T10:00:00%2B03:00&end=${isoDate(start)}T14:00:00%2B03:00`,
    `category=offices&start_date=${isoDate(start)}&months=6`,
    `q=${pick(["nyumba", "apartment", "gari", "hema", "ukumbi"])}`,
    `region=${pick(REGIONS)}&price_min=20000&price_max=200000`,
  ];
}

export default function () {
  const query = pick(queries());
  const sort = `sort=${pick(SORTS)}&page=${1 + Math.floor(Math.random() * 3)}`;
  const url = `${BASE_URL}/api/v1/listings/search?${query}${query ? "&" : ""}${sort}`;
  const res = http.get(url, { tags: { name: "search" }, headers: { "Accept-Language": "sw" } });
  check(res, { "status 200": (r) => r.status === 200 });
}
