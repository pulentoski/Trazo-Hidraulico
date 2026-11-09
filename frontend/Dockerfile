# syntax=docker/dockerfile:1
FROM node:22.23.4-trixie-slim AS deps
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false NPM_CONFIG_FUND=false NPM_CONFIG_AUDIT=false
COPY package.json package-lock.json ./
RUN npm ci

# Imagen de verificación: tsc --noEmit y tipos OpenAPI al día.
FROM deps AS test
COPY . .
USER node
CMD ["sh", "./scripts/check.sh"]

FROM deps AS build
COPY . .
ARG VITE_GOOGLE_MAPS_API_KEY=""
ARG VITE_GOOGLE_MAPS_MAP_ID=""
ARG VITE_DEFAULT_MAP_CENTER_LAT="-33.4489"
ARG VITE_DEFAULT_MAP_CENTER_LNG="-70.6693"
ENV VITE_GOOGLE_MAPS_API_KEY=${VITE_GOOGLE_MAPS_API_KEY} \
    VITE_GOOGLE_MAPS_MAP_ID=${VITE_GOOGLE_MAPS_MAP_ID} \
    VITE_DEFAULT_MAP_CENTER_LAT=${VITE_DEFAULT_MAP_CENTER_LAT} \
    VITE_DEFAULT_MAP_CENTER_LNG=${VITE_DEFAULT_MAP_CENTER_LNG}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
