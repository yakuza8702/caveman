# ---------- build stage: compile caveman-proxy from fork source ----------
FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" \
    -o /out/caveman-proxy ./proxy/cmd/caveman-proxy

# ---------- runtime stage ----------
FROM python:3.12-slim
COPY --from=build /out/caveman-proxy /usr/local/bin/caveman-proxy
COPY proxy/caveman.yaml.tmpl /etc/caveman/caveman.yaml.tmpl
COPY proxy/wrapper.py   /usr/local/bin/wrapper.py
COPY proxy/entrypoint.sh /entrypoint.sh
RUN chmod +x /usr/local/bin/wrapper.py /entrypoint.sh

# runtime defaults — override at run time via .env / compose env
ENV CAVEMAN_MODE=compress
ENV CAVEMAN_LISTEN=127.0.0.1:8788
ENV CAVEMAN_UPSTREAM_NAME=openrouter
ENV CAVEMAN_UPSTREAM_BASE_URL=https://openrouter.ai/api/v1
ENV CAVEMAN_API_KEY_ENV=OPENROUTER_API_KEY
ENV CAVEMAN_UPSTREAM=http://127.0.0.1:8788/compat/openrouter/v1/chat/completions
ENV WRAPPER_LISTEN=0.0.0.0:8787
ENV UPSTREAM_MODELS=https://openrouter.ai/api/v1/models

EXPOSE 8787
ENTRYPOINT ["/entrypoint.sh"]
