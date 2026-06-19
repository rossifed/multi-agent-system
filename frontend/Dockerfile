# Frontend image: build the SPA with bun, serve the static bundle with nginx.
# The API base URL is inlined at BUILD time (Vite), so it is passed as a build arg.
FROM oven/bun:1 AS build
WORKDIR /app

COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile || bun install

COPY . .

# Backend URL the browser will call. Override at build: --build-arg VITE_API_BASE_URL=...
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN bun run build

FROM nginx:alpine AS serve
# nginx:alpine renders templates in /etc/nginx/templates with envsubst at startup,
# so it can listen on Railway's dynamic ${PORT}.
COPY --from=build /app/dist /usr/share/nginx/html
COPY default.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=80
EXPOSE 80
