# =============================================================================
# AIVIS.ONE Frontend -- Dockerfile
# Multi-stage: node build -> nginx serve
# =============================================================================

# -- Build stage --
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .
RUN npm run build

# -- Serve stage --
FROM nginx:alpine

# The build is served under /app/ (vite.config.ts base); see nginx.conf.
COPY --from=build /app/dist /usr/share/nginx/html/app
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
