# Frontend tier: a static page served by nginx, which also forwards /api/ to the backend.
# The "unprivileged" image runs as a non-root user (101) and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.29-alpine

# Pick up security fixes released after the base image was built. Needs root, so switch
# back to the image's non-root user straight after.
USER root
RUN apk upgrade --no-cache
USER 101

COPY index.html /usr/share/nginx/html/index.html
COPY default.conf.template /etc/nginx/templates/default.conf.template

# Overridden by the chart with the backend Service's address.
ENV BACKEND_URL=http://demo-api:80
EXPOSE 8080
