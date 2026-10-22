# Frontend Next.js — Phase 18. Build từ thư mục gốc repo: `docker compose up -d --build`.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
# NEXT_PUBLIC_* được "đóng băng" vào bundle lúc build → phải truyền qua build arg.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
COPY --from=build --chown=node /app/package.json ./
COPY --from=build --chown=node /app/node_modules ./node_modules
COPY --from=build --chown=node /app/.next ./.next
COPY --from=build --chown=node /app/public ./public
COPY --from=build --chown=node /app/next.config.ts ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
CMD ["npm", "run", "start"]
