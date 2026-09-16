FROM node:22-alpine AS base

# Step 1. Install dependencies
FROM base AS deps

WORKDIR /app

RUN corepack enable pnpm

# Copy workspace root manifests
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./

# Copy package manifests for all workspace packages (for layer caching)
COPY packages/api-client/package.json ./packages/api-client/
COPY packages/auth/package.json ./packages/auth/
COPY packages/components/package.json ./packages/components/
COPY packages/core/package.json ./packages/core/
COPY packages/ui/package.json ./packages/ui/

# Copy app manifests
COPY apps/web/package.json ./apps/web/

RUN pnpm install --frozen-lockfile

# Step 2. Build the target app
FROM base AS builder

ARG APP_NAME
ENV APP_NAME=$APP_NAME

WORKDIR /app

RUN corepack enable pnpm

COPY --from=deps /app/package.json /app/pnpm-workspace.yaml /app/pnpm-lock.yaml ./
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

# pnpm installs each workspace project's dependencies into that project's own
# node_modules, and the root holds almost nothing. Without these the builder
# resolves nothing for the packages: @app/ui would have no @base-ui/react,
# @app/core no clsx. Nothing in CI builds this image, so a miss here surfaces
# only on a real deploy.
COPY --from=deps /app/packages/api-client/node_modules ./packages/api-client/node_modules
COPY --from=deps /app/packages/auth/node_modules ./packages/auth/node_modules
COPY --from=deps /app/packages/components/node_modules ./packages/components/node_modules
COPY --from=deps /app/packages/core/node_modules ./packages/core/node_modules
COPY --from=deps /app/packages/ui/node_modules ./packages/ui/node_modules

# Copy shared packages source
COPY packages ./packages

# Copy the app
COPY apps ./apps

# Environment variables must be present at build time
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

ARG NEXT_PUBLIC_CLERK_SIGN_IN_URL
ENV NEXT_PUBLIC_CLERK_SIGN_IN_URL=$NEXT_PUBLIC_CLERK_SIGN_IN_URL

ARG NEXT_PUBLIC_CLERK_SIGN_UP_URL
ENV NEXT_PUBLIC_CLERK_SIGN_UP_URL=$NEXT_PUBLIC_CLERK_SIGN_UP_URL

ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm --filter $APP_NAME build

# Step 3. Production image
FROM base AS runner

ARG APP_NAME
ENV APP_NAME=$APP_NAME

WORKDIR /app

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
USER nextjs

COPY --from=builder --chown=nextjs:nodejs /app/apps/$APP_NAME/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/$APP_NAME/.next/static ./apps/$APP_NAME/.next/static
COPY --from=builder /app/apps/$APP_NAME/public ./apps/$APP_NAME/public

ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000
ENV PORT=3000

CMD node apps/$APP_NAME/server.js
