# Frontend - Claude Code Instructions

## Running

```bash
npm run dev          # dev server http://localhost:5173
npm run build        # production build
npm run lint         # ESLint
npx tsc --noEmit    # type check only
```

## Architecture

### Module Structure
Each feature lives in `src/modules/<feature>/`:
- `<Feature>Page.tsx` - main page component (route target)
- Additional components co-located in the same directory

### State Management
- **Auth state**: Zustand store in `src/shared/hooks/useAuth.ts`
- **Server state**: React Query (`@tanstack/react-query`) for all API data
- **Local UI state**: React useState/useReducer within components

### API Layer
- HTTP client: `src/shared/api/client.ts` (Axios instance)
- Auth token injected automatically via Axios interceptor
- Base URL from `VITE_API_BASE_URL` env var

### Routing
- React Router v6 in `src/App.tsx`
- Protected routes wrapped with auth check
- Module pages lazy-loaded

## Conventions

### Components
- Functional components only (no class components)
- PascalCase for component names and files
- Props interfaces defined above the component
- Use `lucide-react` for icons

### Styling
- TailwindCSS utility classes exclusively
- No CSS modules, no styled-components
- Responsive: mobile-first approach
- Color palette defined in `tailwind.config.js`

### Data Fetching
- Use React Query hooks (`useQuery`, `useMutation`)
- API calls via the shared Axios client
- Optimistic updates for user-facing mutations where appropriate

### i18n
- Multi-language support via `src/shared/i18n.tsx`
- Currently supports: English (en), Chinese (zh)
- All user-facing strings should use translation keys

## Key Files

- `src/App.tsx` - Route definitions, layout structure
- `src/shared/hooks/useAuth.ts` - Auth store (login, logout, token, role)
- `src/shared/hooks/useWebSocket.ts` - Scanner WebSocket hook
- `src/shared/api/client.ts` - Axios HTTP client
- `src/shared/components/DataTable.tsx` - Reusable table component
- `src/shared/components/Layout.tsx` - App shell (nav, sidebar)
- `src/scanner/BarcodeScanner.tsx` - Camera barcode scanning (large file)

## Adding a New Module

1. Create `src/modules/<feature>/<Feature>Page.tsx`
2. Add route in `src/App.tsx`
3. Add nav link in `Layout.tsx` sidebar (if needed)
4. Use React Query for data fetching from backend API
