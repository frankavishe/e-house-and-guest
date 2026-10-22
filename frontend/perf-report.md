# Frontend performance (T146, Principle VI, SC-002)

Targets: ≤ 300 KB gz initial JS per route; LCP < 2 s on a slow 3G phone for home, search and
listing pages.

Measured 2026-10-22 on a dev laptop, production build (`next build` + `next start`) against the
compose API with ~20,000 listings (`app.seed_perf`).

## JS budget

`npm run build` First Load JS (gz), the full set a cold visit downloads:

| Route | First Load JS |
|---|---|
| shared by all | 103 KB |
| `/[locale]` (home) | 124 KB |
| `/[locale]/search` | 125 KB |
| `/[locale]/l/[id]` | 131 KB |
| largest: `/[locale]/owner/listings/[id]/edit` | 134 KB |

Every route is under half the budget. `npm run size` enforces 300 KB per entry. Leaflet (JS and
its 2.8 KB gz CSS) loads only when a map is opened (`next/dynamic`, `SearchMapLoader`).

## Lighthouse

Lighthouse 12.8.2, mobile form factor, 4× CPU slowdown, headless Chrome, **DevTools throttling**
(real packet-level throttling; request latency = RTT × 3.75, throughput × 0.9, as Lighthouse does
for its own presets). LCP in ms; ranges are two runs of the final build.

| Network | Home | Search | Listing |
|---|---|---|---|
| Slow 3G (400 ms RTT, 400 Kbps) | 2,001–2,117 | 2,096–2,151 | 2,058–2,099 |
| Regular 3G (300 ms, 700 Kbps) | 1,608–1,610 ✓ | 1,641–1,704 ✓ | 1,588–1,590 ✓ |
| Slow 4G, Lighthouse default (150 ms, 1.6 Mbps) | 1,038–1,095 ✓ | 996–1,051 ✓ | 1,017–1,094 ✓ |

Every run also showed:

- CLS 0
- TBT 160–430 ms
- page weight 182–204 KB
- performance scores 87–97

**Result:** LCP is under 2 s on regular 3G (SC-002's "typical 3G") and slow 4G. On strict slow 3G
it lands at 2.0–2.15 s, about 0.1 s over. The floor there is the network itself: DevTools adds
1.5 s of latency to the document request, which leaves 0.5 s to stream about 24 KB of HTML and
paint. Run-to-run noise is about ±100 ms.

The LCP element is text on all three pages: the tagline, a card's location line and the listing
title. A listing with real photos makes the first gallery image the LCP candidate. That image
already loads eagerly with `fetchpriority="high"`, plus a 320/640/1280 `srcset`.

Lighthouse's default *simulated* throttling reported 6.4–7.4 s for the same pages. That number is
an artifact of measuring on localhost. Every script finished before first paint, so the simulator
treats all of them as LCP dependencies. Its own breakdown put 81 % of LCP in "render delay"
despite no render-blocking resources and no web fonts. The DevTools numbers above are what a
throttled phone actually sees.

## Changes

1. **Inline CSS (`experimental.inlineCss`).** The whole Tailwind stylesheet is 6 KB gz. With
   inlining there is no render-blocking CSS request, which on slow networks is a full round trip.
   Measured with a linked stylesheet instead:
   - slow 3G: about 4.0 s instead of 2.1 s
   - regular 3G: about 3.1 s instead of 1.6 s
   - slow 4G: about 1.8 s instead of 1.0 s

   The cost: Next also repeats the CSS inside the RSC payload, about 6 KB gz per HTML document.
2. **Client messages split by section.** Before, `NextIntlClientProvider` sent the whole
   catalogue (31 KB, every owner and admin string) inside every page's HTML. Now
   `src/i18n/ClientMessages.tsx` sends only the namespaces each section's client components use
   (`src/i18n/client-messages.ts`). Home and search need about 0.7 KB.
   - Home HTML went from 33.0 KB gz to 24.0 KB gz (−27 %), and every other page loses about 9 KB.
   - LCP did not move measurably: an A/B with the full catalogue stayed within run-to-run noise.
     The gain is data cost on metered mobile plans and less to parse.
   - `tests/unit/client-messages.test.ts` walks each route's imports and fails if a client
     component (including components without "use client" that a client one imports) uses a namespace its
     section doesn't send.
3. **Listing card `sizes`.** It said `(min-width: 640px) 320px`, but cards in the 2-column
   640–1023 px layout are up to about 490 px wide, so tablets got a blurry 320w image. The value
   now matches the grid: `(min-width: 1024px) 320px, (min-width: 640px) calc(50vw - 24px),
   calc(100vw - 32px)`. The other `sizes` values were already right: the gallery is
   `(min-width: 640px) 600px, 90vw`, and the fixed-size thumbnails use the 320 variant.

## Not done / follow-ups

- **Production TTFB.** Serve the SSG pages (home, browse) from a CDN edge near Tanzanian users.
  On real networks DNS, TLS and distance add to the latency the localhost runs don't see.
- **Search page size.** 20 cards make the search HTML 43 KB gz, because each card appears in both
  the markup and the RSC payload. 12 per page on mobile would cut it by about a third. That's a
  product call.
- **The CSS copy in the RSC payload** comes from Next's `inlineCss`. Revisit when it leaves
  experimental.

## Reproduce

```bash
cd frontend
API_INTERNAL_URL=http://localhost:8010 S3_PUBLIC_BASE_URL=http://localhost:9010/public npm run build
npm run size
API_INTERNAL_URL=http://localhost:8010 npx next start -p 3020
# slow 3G: request latency 400×3.75 ms, throughput 400×0.9 Kbps
CHROME_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe" npx lighthouse@12.8.2 \
  http://localhost:3020/sw --only-categories=performance --form-factor=mobile \
  --throttling-method=devtools --throttling.requestLatencyMs=1500 \
  --throttling.downloadThroughputKbps=360 --throttling.uploadThroughputKbps=360 \
  --throttling.cpuSlowdownMultiplier=4 --view
```
