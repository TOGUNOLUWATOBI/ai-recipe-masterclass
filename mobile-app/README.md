# Recipe RAG — Mobile App

React Native (Expo) client for the recipe RAG pipeline at `recipe.bebs.dev`. Three tabs,
each backed by `pipeline-service`:

- **Tilbud** (home tab) — a 3-level drilldown through current Kassalapp grocery
  discounts, Mattilbud-style: first a list of stores currently running deals (logo, name,
  deal count), then tap a store to see that store's discounted items in a 2-column grid
  (product photo, price crossed out against the discounted price, and a `-X%` badge —
  `GET /recipes/discounted`), then tap an item to push into a detail screen that
  generates a recipe for exactly that product on demand
  (`POST /recipes/from-ingredients`) — recipes are never generated for the whole list up
  front, only for what you actually open.
- **Ask** — free-text question → grounded or best-effort recipe answer (`POST /query`)
- **Ingredients** — comma-separated ingredient list → matching corpus recipes, or
  LLM-generated suggestions if nothing matches (`POST /recipes/from-ingredients`)

## Why Tilbud is the home tab

Modeled after Mattilbud, the Norwegian weekly grocery-flyer app — familiar territory for
users used to browsing "ukens tilbud" by store rather than typing free-text questions.
The tab is a 3-level drilldown: `StoresScreen` shows a list of stores currently running
deals (one tile per store, with a deal count) → tap a store to open `StoreItemsScreen`,
a grid of that store's discounted items → tap an item to open `DealDetailScreen`, which
generates a recipe for it on demand. The backend caches the discount scan and refreshes
it once a day via cron (see the root project's README, "Grocery discount caching")
rather than scanning Kassalapp live on every request, so the stores list loads in well
under a second and can safely auto-fetch on screen mount instead of requiring a manual
"check today's deals" button press like the old design needed.

## Running

```bash
npm install
npm start          # Expo dev server — press w/i/a, or scan the QR code with Expo Go
npm run web         # web directly
npm run ios         # iOS Simulator
npm run android     # Android emulator
```

Points at the live production backend (`https://recipe.bebs.dev`) by default — no local
backend setup needed to try the app.

## Testing

```bash
npm run typecheck   # tsc --noEmit
npm test            # Jest + React Native Testing Library (55 tests)
```

Test coverage: input validation (`src/api/validation.ts`), the API client's error
classification and the `include_recipes` fast-path flag (`src/api/client.ts`), the
`DealCard`/`StoreCard` components, and all five screens (render, submit/tap,
loading/error states, double-submit guarding, store grouping, navigation from stores to
store items to the deal detail screen).

Verified separately (not part of the automated suite, since it hits the live network): a
full `expo export -p web` production bundle, and live end-to-end calls to all endpoints
confirming response shapes match `src/types/api.ts` — including that `/recipes/discounted
?include_recipes=false` now returns in well under a second (cache read) versus the ~90s a
live Kassalapp scan used to take.

## Security notes

- **Backend URL is fixed, not user-configurable** (`src/config.ts`) — HTTPS only, no
  settings screen that could let something redirect requests elsewhere.
- **Every request has a hard timeout** (`AbortController`, 60s for `/query` and
  `/recipes/from-ingredients`, 180s for `/recipes/discounted` when recipes are requested),
  so a hung request can't leave the app stuck indefinitely.
- **All failure modes are classified**, not just caught: network-down, timeout, non-2xx
  HTTP status, and malformed JSON each map to a distinct `ApiError.kind` and a safe,
  generic user-facing message (`src/api/errors.ts`) — raw backend error bodies and stack
  traces never reach the UI.
- **Client-side input validation** (length/count caps in `src/api/validation.ts`) is a
  UX/robustness guard against wasting a slow LLM call on empty or absurd input — it is
  explicitly not treated as a security boundary; the backend is not assumed safe merely
  because the app validates first. The per-deal recipe request (`DealDetailScreen`) goes
  through this same validation even though the product name originates from the backend,
  not free-typed user input.
- **Runtime response validation**: light type guards on every API response
  (`src/api/client.ts`) so a malformed or unexpected backend payload throws a typed error
  instead of crashing the UI.
- **No secrets in the app**: nothing here needs an API key — the app only talks to
  `pipeline-service`, which holds the Kassalapp key server-side.
- **No injection surface**: recipe text renders exclusively through React Native `<Text>`;
  product/store images load through the standard `<Image>` component (an HTTP(S) GET, no
  script execution) from Kassalapp/store CDN URLs the backend supplies — never a
  user-typed URL. No `WebView`, no HTML rendering, no `eval`.
- Backend CORS (`pipeline_server.py`) is deliberately permissive (`allow_origins=["*"]`)
  — safe specifically because the API has no auth/session/cookie model to protect;
  restricting CORS would only inconvenience this app's web build without stopping the
  same request made via curl.
- The daily discount-cache refresh (backend) runs only via a host cron job over SSH —
  deliberately **not** exposed as a public HTTP endpoint, so nothing external can trigger
  repeated Kassalapp scans and burn its rate limit.
- `npm audit` shows 10 moderate advisories, all in Expo's own build-time tooling chain
  (`uuid` → `xcode` → `@expo/config-plugins`, used only by `expo prebuild`/CLI, never
  bundled into the shipped app — confirmed via `expo export -p web`, whose output bundle
  contains no reference to any of that chain).

## Layout

```
src/
  config.ts              backend base URL + timeouts
  types/api.ts            response types, hand-synced to pipeline_server.py
  api/
    client.ts              fetch wrapper: timeout, error classification, response validation
    errors.ts               ApiError + user-facing message mapping
    validation.ts           client-side input sanitization
  components/
    DealCard.tsx             Mattilbud-style price-tag card (photo, price, -X% badge)
    StoreCard.tsx             tappable store tile (logo, name, deal count) for the stores list
    RecipeCard.tsx           parses/renders a recipe (title/ingredients/instructions)
    ErrorBanner.tsx
  screens/
    StoresScreen.tsx         home tab — list of stores with deal counts, auto-loads from cache
    StoreItemsScreen.tsx      per-store 2-column grid of DealCards, pushed on tapping a store
    DealDetailScreen.tsx      pushed on tapping an item — generates a recipe for that one product
    AskScreen.tsx, IngredientsScreen.tsx
  navigation/
    AppNavigator.tsx          bottom tabs: Tilbud, Ask, Ingredients
    TilbudStackNavigator.tsx  stack nested in the Tilbud tab: StoresList → StoreItems → DealDetail
    types.ts                  shared navigation param types
  utils/parseRecipeText.ts   best-effort recipe text parsing (tolerant of format variants)
__tests__/                  mirrors src/, one test file per module/screen/component
```
