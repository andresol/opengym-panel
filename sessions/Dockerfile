FROM node@sha256:ec857ea6bb60cb3d0fa4d97495590c5fe7d51be8572c307b55957eeb06569cf7
WORKDIR /app
COPY --chown=node:node package.json /app/package.json
COPY --chown=node:node sessions/ /app/sessions/
COPY --chown=node:node bridge/ /app/bridge/
COPY --chown=node:node preview/names.mjs /app/preview/names.mjs
COPY --chown=node:node vendor/opengym/ /app/vendor/opengym/
USER node
CMD ["node", "/app/sessions/server.mjs"]
