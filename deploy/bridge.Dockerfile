# WhatsApp linked-device bridge (Baileys, pinned). No install scripts run.
FROM node:22-bookworm-slim
ENV NODE_ENV=production BRIDGE_HOST=0.0.0.0 WA_SESSION_DIR=/session MEDIA_ENABLED=0
WORKDIR /app
COPY wa-bridge/package.json wa-bridge/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY wa-bridge/src ./src
RUN mkdir -p /session && chown node /session
USER node
EXPOSE 8200
CMD ["node", "src/bridge.js"]
