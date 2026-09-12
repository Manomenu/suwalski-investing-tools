# Build context is the SOLUTION ROOT, matching the server image so both build from one
# place:
#
#   podman build -f suwalski_investing_web/Dockerfile -t suwalski-web .

FROM docker.io/library/node:24-alpine AS builder

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

WORKDIR /app

# pnpm 11 reads its settings out of pnpm-workspace.yaml, so it belongs in the install
# layer alongside the manifest and the lockfile.
COPY suwalski_investing_web/package.json suwalski_investing_web/pnpm-lock.yaml suwalski_investing_web/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY suwalski_investing_web/ ./
# `pnpm build` is `tsc --noEmit && vite build`: a type error fails the image rather than
# the deploy.
RUN pnpm build


FROM docker.io/nginxinc/nginx-unprivileged:1.29-alpine

# The entrypoint expands templates with envsubst. Without this filter it would also eat
# nginx's own $host, $uri and $scheme.
ENV NGINX_ENVSUBST_FILTER="^API_UPSTREAM$"
ENV API_UPSTREAM="http://server:6100"

COPY --from=builder /app/dist /usr/share/nginx/html
COPY suwalski_investing_web/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080
