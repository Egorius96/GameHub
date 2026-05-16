# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_API_BASE
ENV VITE_API_BASE=$VITE_API_BASE
# При ENETUNREACH: --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN npm config set registry "${NPM_REGISTRY}" \
  && npm config set fetch-retries 5 \
  && npm config set fetch-retry-mintimeout 20000 \
  && npm config set fetch-retry-maxtimeout 120000
COPY package.json package-lock.json tsconfig.json vite.config.ts index.html /app/
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY src /app/src
COPY public /app/public
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx-default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
