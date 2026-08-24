FROM node:22-alpine

WORKDIR /app

COPY package.json ./
COPY server.mjs ./
COPY fixtures ./fixtures
COPY public ./public
COPY scripts ./scripts

ENV NODE_ENV=production
ENV PORT=4179

EXPOSE 4179

CMD ["npm", "start"]
