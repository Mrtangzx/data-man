FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html
HEALTHCHECK --interval=3s --timeout=2s --retries=20 CMD wget -q -O - http://127.0.0.1/healthz >/dev/null || exit 1
