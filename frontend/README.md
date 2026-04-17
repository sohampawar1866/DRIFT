# DRIFT Frontend

Frontend UI for DRIFT, built with Vite + React + TypeScript.

## Local Development

1. Install dependencies:

```bash
npm install
```

2. Start dev server:

```bash
npm run dev
```

By default, Vite proxies API requests from `/api/*` to `http://localhost:8000`.

## Endpoint Configuration

The frontend now resolves endpoints safely for all environments (dev, staging, prod).

- `VITE_API_PREFIX`: API path prefix. Default: `/api/v1`
- `VITE_API_BASE_URL`: Optional runtime API base URL
- `VITE_DEV_API_TARGET`: Dev-only proxy target for Vite server

### Recommended setups

1. Local dev with backend on `localhost:8000`:

- leave everything unset

2. Backend at custom host in dev:

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:9000 npm run dev
```

3. Deployed frontend with absolute API host:

```bash
VITE_API_BASE_URL=https://api.example.com
```

4. If your base URL already includes `/api/v1`:

```bash
VITE_API_BASE_URL=https://api.example.com/api/v1
```

No duplicated prefix will be added.

## Build

```bash
npm run build
npm run preview
```
