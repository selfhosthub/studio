# ui/Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Builder
FROM node:24-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG SHS_API_BASE_URL
ARG SHS_WS_URL
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ENV SHS_API_BASE_URL=${SHS_API_BASE_URL}
ENV SHS_WS_URL=${SHS_WS_URL}
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN npm run build

# Stage 2: Runner
FROM node:24-alpine AS runner
WORKDIR /app

# Patch base-image CVEs the upstream tag has not picked up yet.
RUN apk upgrade --no-cache libcrypto3 libssl3

# Standalone runtime execs node directly; drop the npm/corepack CLIs
RUN rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

LABEL org.opencontainers.image.title="Self-Host Studio UI" \
      org.opencontainers.image.vendor="Self-Host Hub" \
      org.opencontainers.image.source="https://github.com/selfhosthub/studio" \
      org.opencontainers.image.licenses="LicenseRef-Studio-Use-License"

ENV NODE_ENV=production
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy necessary files
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Runtime env injection entrypoint
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Image carries the UI source, so the license notice ships with it.
COPY LICENSE LEGAL.md /app/

# Change ownership to nextjs user
RUN chown -R nextjs:nodejs /app

# Switch to nextjs user
USER nextjs

# Expose port
EXPOSE 3000

# Set hostname
ENV HOSTNAME="0.0.0.0"

# Start the application - entrypoint writes __env.js then execs node
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["node", "server.js"]
