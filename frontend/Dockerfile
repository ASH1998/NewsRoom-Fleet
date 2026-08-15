# Newsroom Fleet editor desk — static build served by nginx on Cloud Run.
#
# nginx proxies /api to the backend service so the browser stays on one origin:
# no CORS preflight in the demo, and no API base URL baked into the bundle.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# BACKEND_URL and PORT are substituted into the template at container start
# (the nginx image runs envsubst over /etc/nginx/templates).
ENV PORT=8080 \
    BACKEND_URL=http://127.0.0.1:8000
EXPOSE 8080
