FROM node:22-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=ui /ui/dist ./ui/dist
ENV OPENRD_HOST=0.0.0.0
ENV OPENRD_UI_DIST=/app/ui/dist
EXPOSE 8080
CMD ["openrd", "serve", "--host", "0.0.0.0", "--port", "8080"]
