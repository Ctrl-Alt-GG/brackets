# Build static files
FROM node:24-bookworm-slim AS builder

WORKDIR /app

ENV NODE_ENV=production

COPY . .

RUN corepack enable && \
    CI=true pnpm install && \
    pnpm build

# Production image, copy all the static files and run nginx as an unprivileged user
FROM nginxinc/nginx-unprivileged:stable-bookworm AS runner

WORKDIR /usr/share/nginx/html

ENV API_BASE_URL=http://localhost:8400/api

COPY --from=builder --chown=101:101 /app/dist/ /usr/share/nginx/html/
COPY ./nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 ./docker-entrypoint.sh /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
