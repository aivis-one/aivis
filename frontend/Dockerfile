# =============================================================================
# AIVIS.ONE Frontend -- Dockerfile
# Multi-stage: node build -> nginx serve
# =============================================================================
#
# THIS SERVER'S ADDRESSES ARE BUILD ARGS (H35 P-127), and the only way in:
#   AIVIS_API_ORIGIN    the API the cabinet calls (VITE_API_BASE_URL) and
#                       that its CSP allows (connect-src)
#   AIVIS_FILES_ORIGIN  the public storage site its CSP allows (img-src)
# Both are exact https origins (frontend/src/api/deployOrigin.ts says what
# that means). They come from docker-compose.yml, which takes them from the
# environment `aivis frontend build` sets (scripts/aivis-manage.sh,
# build_frontend_image). Nothing in this directory carries a value: a build
# without one stops at the first RUN below with the variable's name.

# -- Build stage --
FROM node:22-alpine AS build

ARG AIVIS_API_ORIGIN
ARG AIVIS_FILES_ORIGIN

# First, before anything is installed: absent or empty stops here, by name.
RUN : "${AIVIS_API_ORIGIN:?AIVIS_API_ORIGIN is not set -- build with: aivis frontend build}" \
 && : "${AIVIS_FILES_ORIGIN:?AIVIS_FILES_ORIGIN is not set -- build with: aivis frontend build}"

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

# The form of both values, by the same rule the bundle and vite.config.ts
# use. The files origin is checked here because only the CSP carries it --
# vite never sees it. Node runs the TypeScript module directly (type
# stripping); the module is written to allow that.
RUN node --input-type=module -e " \
      const { requireOrigin } = await import('./src/api/deployOrigin.ts'); \
      for (const name of ['AIVIS_API_ORIGIN', 'AIVIS_FILES_ORIGIN']) \
        requireOrigin(name, process.env[name], { allowHttp: false });"

# vite.config.ts checks VITE_API_BASE_URL again for every production build,
# this one included.
RUN VITE_API_BASE_URL="$AIVIS_API_ORIGIN" npm run build

# -- Serve stage --
FROM nginx:alpine

ARG AIVIS_API_ORIGIN
ARG AIVIS_FILES_ORIGIN

# The build is served under /app/ (vite.config.ts base); see nginx.conf.
COPY --from=build /app/dist /usr/share/nginx/html/app

# nginx.conf is a template with exactly two placeholders. envsubst is given
# their names and nothing else, so nginx's own $variables pass through. A
# placeholder left over (a misspelt name) stops the build, and so does a
# rendered config nginx would refuse.
COPY nginx.conf /tmp/nginx.conf.template
RUN envsubst '${AIVIS_API_ORIGIN} ${AIVIS_FILES_ORIGIN}' \
        < /tmp/nginx.conf.template > /etc/nginx/conf.d/default.conf \
 && rm /tmp/nginx.conf.template \
 && if grep -n '\${AIVIS_' /etc/nginx/conf.d/default.conf; then \
        echo "nginx.conf: a placeholder above was not rendered" >&2; exit 1; \
    fi \
 && nginx -t

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
