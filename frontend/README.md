# CBSHOME Frontend

Vue 3 + TypeScript + Vite SPA for the CBSHOME investment platform.

## Stack

- **Framework:** Vue 3 (Composition API)
- **Language:** TypeScript 5.x (strict)
- **Build:** Vite 6
- **Routing:** Vue Router 4
- **State:** Pinia
- **i18n:** vue-i18n 10 (en/ru/de/ar + RTL)
- **Styles:** Custom CSS design system (no CSS frameworks)
- **PWA:** vite-plugin-pwa

## Development

Development and deployment happen on VPS via `aivis update`.

```bash
# Local dev (if needed)
npm ci
npm run dev          # http://localhost:5173
npm run build        # Production build
npm run lint         # ESLint + Prettier check
npm run lint:fix     # Auto-fix
npm run type-check   # TypeScript check
```

## Deployment

Managed by `scripts/install_aivis.sh` and `aivis update`.

```
aivis update    # git pull -> docker compose build -> restart
aivis logs frontend
aivis status
```

## Environment

Copy `.env.example` to `.env` and configure:

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend API URL (e.g. `https://api.cbshome.org`) |
| `VITE_TELEGRAM_BOT_URL` | Telegram bot deep link |
