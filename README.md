<p align="center">
  <img src="assets/images/roofgrid-wordmark.png" alt="RoofGrid" width="240">
</p>

<p align="center">
  Access-aware rooftop solar planning with editable energy, financial, and environmental assumptions.
</p>

## What RoofGrid does

RoofGrid helps you turn a real rooftop into an early-stage solar plan. Search for an address, select or draw a roof, reserve access and maintenance space, mark obstacles, and arrange panels inside the usable area. The planner then estimates system capacity, energy generation, savings, payback, and avoided emissions.

RoofGrid is a planning and exploration tool, not an engineering design, structural assessment, permit set, or installer quote.

## Features

- Satellite mapping with worldwide address search and GPS support
- OpenStreetMap building-footprint detection and manual roof drawing
- Rooftop access points, maintenance paths, and obstacle exclusions
- Configurable panel specifications and layout controls
- NASA POWER solar-resource and temperature data
- Editable local currency, tariff, export-credit, cost, usage, and emissions inputs
- Energy, financial, and environmental estimates
- Optional AI assistant through Groq or another OpenAI-compatible API
- Downloadable PDF reports
- Responsive landing page and planning workspace

## Technology

| Area | Implementation |
| --- | --- |
| Frontend | HTML, CSS, and vanilla JavaScript |
| Maps and geometry | Leaflet, Esri World Imagery, OpenStreetMap, Turf.js |
| Solar data | NASA POWER API with bundled regional fallback data |
| Local server | Python standard library HTTP server and private API proxies |
| Deployment | Vercel static hosting and Python serverless functions |
| AI | Server-side OpenAI-compatible chat-completions proxy; Groq by default |
| Reports | jsPDF and html2canvas |

## Run locally

Requirements: Python 3.9 or newer and a modern browser.

```bash
git clone git@github.com:rohanmalhotracodes/RoofGrid.git
cd RoofGrid
cp .env.example .env.local
python3 server_local.py
```

Then open:

- Landing page: <http://localhost:8000/index.html>
- Planner: <http://localhost:8000/solar_advanced.html>

Use `server_local.py` instead of opening the HTML file directly or running a basic static-file server. RoofGrid's AI, OpenStreetMap, and NASA requests use its local proxy routes.

## Configure Groq AI

AI chat is optional; mapping and solar calculations work without it.

1. Copy the example environment file:

   ```bash
   cp .env.example .env.local
   ```

2. Add your Groq key to `.env.local`:

   ```dotenv
   AI_PROVIDER=groq
   GROQ_API_KEY=gsk_your_real_key
   AI_MODEL=openai/gpt-oss-120b
   ```

   To enable contact-form delivery, also set the private recipient:

   ```dotenv
   CONTACT_EMAIL=you@example.com
   ```

3. Restart `python3 server_local.py` after changing the file.

`.env.local` is ignored by Git. Never put a real API key in `.env.example`, frontend JavaScript, or a committed file.

For another OpenAI-compatible provider, set `AI_PROVIDER`, `AI_API_KEY`, `AI_BASE_URL`, and `AI_MODEL`. Optional `AI_AUTH_HEADER`, `AI_AUTH_SCHEME`, and `AI_ALLOW_NO_AUTH` settings are documented in `.env.example`.

## Deploy to Vercel

The included `vercel.json` serves the site and maps private proxy routes to the Python functions in `api/`.

1. Import this repository into Vercel.
2. Add `GROQ_API_KEY` and `CONTACT_EMAIL` in the Vercel project's environment variables.
3. Optionally add `AI_PROVIDER` and `AI_MODEL` if you do not want the defaults.
4. Redeploy after changing environment variables.

Do not prefix server-side environment variables with `NEXT_PUBLIC_` or otherwise expose them to browser code.

## Project structure

```text
.
├── api/                    # Vercel Python proxy functions
├── assets/                 # Current RoofGrid logos and page imagery
├── data/Weather Data/      # Bundled NASA POWER fallback datasets
├── index.html              # Landing page
├── privacy.html            # Privacy policy
├── solar_advanced.html     # Rooftop planner
├── server_local.py         # Local static server and API proxies
├── sw.js                   # Service worker
└── vercel.json             # Vercel routes and headers
```

## Data and planning limitations

- Satellite imagery and OpenStreetMap outlines may be incomplete or outdated.
- Solar production and financial outputs depend on the assumptions entered by the user.
- Confirm roof structure, shading, fire setbacks, electrical requirements, permits, tariffs, and equipment choices with qualified local professionals.
- AI responses may be inaccurate and should not replace local regulations, utility guidance, or professional advice.

## License

RoofGrid is available under the [MIT License](LICENSE).
