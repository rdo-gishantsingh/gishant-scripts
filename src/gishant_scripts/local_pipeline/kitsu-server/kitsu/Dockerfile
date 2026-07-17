# Stage 1: Build the Vue.js application
FROM node:18 AS build-stage

WORKDIR /app

# Copy package.json and lock files
COPY package*.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy project files
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the application with Nginx
FROM nginx:alpine AS production-stage

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from build-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy custom nginx configuration
# We assume the nginx.conf is passed from the build context relative path or we will mount it in compose
# But based on the plan, we are putting nginx.conf in a separate dir.
# actually, it's safer to rely on volume mount for config in compose, or copy it if it's in the build context.
# Since the build context for this dockerfile is the kitsu repo, we don't have the nginx.conf there.
# So we will rely on the docker-compose to mount the nginx.conf, OR we create a generic one here.
# Let's just expose port 80 and let compose handle the config mount.

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
