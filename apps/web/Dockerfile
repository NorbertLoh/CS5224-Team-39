# syntax=docker/dockerfile:1
FROM node:24-alpine AS development
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY --chown=node:node . .
# Frontend imports resolve the shared repository contracts outside the app root.
COPY --from=contracts --chown=node:node . /contracts
RUN npm run build
EXPOSE 5173
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=12 CMD node -e "fetch('http://127.0.0.1:5173/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
