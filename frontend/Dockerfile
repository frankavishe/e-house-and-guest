# Multi-stage: the default final stage is the production standalone server (docker-compose.yml);
# the `dev` target runs `next dev` with hot reload (docker-compose.dev.yml).
FROM node:22-alpine AS deps
# Match the npm that writes package-lock.json (see "packageManager" in package.json).
RUN npm install -g npm@11.12.1 --no-audit --no-fund
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM deps AS dev
ENV NEXT_TELEMETRY_DISABLED=1
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
# next.config.ts resolves the /api rewrite target and the image host at build time.
ARG API_INTERNAL_URL=http://localhost:8000
ARG S3_PUBLIC_BASE_URL=http://localhost:9000/public
ARG NEXT_PUBLIC_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
ENV API_INTERNAL_URL=$API_INTERNAL_URL S3_PUBLIC_BASE_URL=$S3_PUBLIC_BASE_URL     NEXT_PUBLIC_TILE_URL=$NEXT_PUBLIC_TILE_URL
COPY . .
RUN mkdir -p public && npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
