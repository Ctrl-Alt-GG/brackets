# Build static files
FROM node:24-bookworm-slim AS builder

WORKDIR /app

# The dependencies first, so their layer is reused when only the source changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Production image, copy all the static files and run nginx as an unprivileged user
FROM nginxinc/nginx-unprivileged:stable-bookworm AS runner

LABEL org.opencontainers.image.description="Bracket frontend for the Ctrl-Alt-GG LAN tournament system: React 19 and Vite SPA served by nginx."

# Empty: the API is on the page's own origin, behind the same reverse proxy.
ENV API_BASE_URL=

COPY --from=builder --chown=101:101 /app/dist/ /usr/share/nginx/html/
# The image's entrypoint runs the scripts in /docker-entrypoint.d and fills in the templates.
COPY ./nginx/templates/ /etc/nginx/templates/
COPY --chmod=755 ./docker-entrypoint.d/ /docker-entrypoint.d/

EXPOSE 8080
