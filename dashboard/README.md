# Anamika Console

Demo and review console for the Anamika pipeline (Next.js 15, React 19, Tailwind v4). It shows one live run:
redaction, identity linkage, the attack simulation, clinical integrity and the security audit.
It is not part of the evaluated pipeline.

## Run

```bash
npm install
npm run demo
```

`npm run demo` builds once, starts the FastAPI service on `127.0.0.1:8001` and the console on
`http://localhost:3000`, and writes a local `.env.local` with a random API key and run secret.
Requires Node.js 20+ and the backend set up with `uv sync` in `../backend`.

## Scripts

| Script | Does |
|---|---|
| `npm run demo` | API + console together (production build) |
| `npm run dev` | console only, development mode (API must already run) |
| `npm run build` / `npm start` | production build and server |
| `npm run lint` / `npm run typecheck` | checks |

## Security

The browser never talks to FastAPI. Route Handlers in `src/app/api/*` call it with a server-side key
(`ANAMIKA_API_URL`, `ANAMIKA_API_KEY`). Original documents are only served when the backend runs with
`ANAMIKA_ALLOW_ORIGINALS=true`, which production refuses. Use synthetic data only.

Design tokens and screen specs: [../docs/DESIGN_SYSTEM.md](../docs/DESIGN_SYSTEM.md).
