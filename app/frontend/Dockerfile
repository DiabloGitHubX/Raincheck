
FROM nginx:stable-alpine

RUN apk upgrade --no-cache

COPY index.html /usr/share/nginx/html/index.html
COPY default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
