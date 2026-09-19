<p align="center">
  <img src="assets/images/roofgrid-wordmark.png" alt="RoofGrid" width="260">
</p>

<p align="center">
  <strong>Turn a real rooftop into a practical, access-aware solar plan.</strong>
</p>

<p align="center">
  Locate a roof, map usable space, place panels, and explore energy, financial, and environmental outcomes in one workflow.
</p>

![RoofGrid landing page showing an access-aware rooftop solar layout](assets/screenshots/landing-page.png)

## Why RoofGrid

Early solar estimates often start and end with a panel count. RoofGrid adds the real constraints that determine whether a rooftop plan is usable: roof geometry, access routes, maintenance space, obstacles, and editable local assumptions.

The result is an early-stage planning workspace that helps property owners, designers, students, and sustainability teams understand a roof's solar potential before moving to detailed engineering.

## From rooftop to decision

1. **Locate** — search globally, use your current location, or navigate directly on the satellite map.
2. **Define** — detect a building footprint or draw the usable roof boundary yourself.
3. **Plan** — reserve rooftop access and maintenance paths, mark obstacles, and configure the panel layout.
4. **Estimate** — review expected generation, system size, cost, savings, payback, and environmental impact.
5. **Explain** — use the optional AI assistant to explore results and identify questions for local professionals.

### Find and define a rooftop

![RoofGrid planner showing global satellite search and roof setup controls](assets/screenshots/planner-setup.png)

### Review energy potential

![RoofGrid energy analysis showing production and solar resource estimates](assets/screenshots/energy-analysis.png)

### Explore financial outcomes

![RoofGrid financial analysis showing cost, savings, return, and payback estimates](assets/screenshots/financial-analysis.png)

### Ask questions about the plan

![RoofGrid AI assistant explaining the financial results for a rooftop plan](assets/screenshots/ai-assistant.png)

## Core capabilities

- Worldwide satellite mapping, address search, and GPS support
- OpenStreetMap building-footprint detection and manual roof drawing
- Access points, maintenance paths, and obstacle exclusion zones
- Configurable panel dimensions, spacing, orientation, and layout density
- NASA POWER solar-resource and temperature data with bundled regional fallbacks
- Editable currency, tariffs, export credit, installation cost, usage, and grid-emissions assumptions
- Energy, financial, and environmental estimates in one planning workspace
- Optional Groq-powered AI assistant and downloadable PDF reports

## Environmental impact and the SDGs

RoofGrid is designed to support better early decisions about distributed solar. It can help users compare how much clean electricity a rooftop may generate, understand whether a layout is practical, and estimate avoided grid emissions using transparent, editable assumptions.

This work aligns with four United Nations Sustainable Development Goals:

| Goal | How RoofGrid contributes |
| --- | --- |
| [SDG 7 — Affordable and Clean Energy](https://sdgs.un.org/goals/goal7) | Makes rooftop renewable-energy potential easier to explore and supports informed investment in solar generation. |
| [SDG 11 — Sustainable Cities and Communities](https://sdgs.un.org/goals/goal11) | Helps evaluate existing urban rooftops as distributed-energy sites while accounting for safe access and maintainability. |
| [SDG 12 — Responsible Consumption and Production](https://sdgs.un.org/goals/goal12) | Encourages efficient use of available roof area and exposes the material, energy, and financial assumptions behind a proposed system. |
| [SDG 13 — Climate Action](https://sdgs.un.org/goals/goal13) | Estimates potential avoided emissions so users can compare rooftop solar scenarios as part of broader decarbonization planning. |

RoofGrid reports estimated annual and lifetime energy generation, avoided CO₂e, and simple environmental equivalents. These values are decision-support estimates—not audited carbon accounting, verified emissions reductions, or certification of SDG performance.

In practical terms, the planner helps quantify:

- how much of a roof can be used without ignoring access and obstacle constraints;
- the renewable electricity a proposed layout may produce;
- the share of local electricity use that solar could cover; and
- the potential emissions avoided under an editable grid-emissions assumption.

## How the estimates are built

| Area | Source or method |
| --- | --- |
| Map and geometry | Leaflet, Esri World Imagery, OpenStreetMap, and Turf.js |
| Solar resource | NASA POWER API with bundled regional fallback data |
| Layout | Browser-based geometry using the selected roof, exclusions, access path, and panel settings |
| Finance | User-editable cost, tariff, export-credit, usage, degradation, and discount assumptions |
| Environmental impact | Estimated generation multiplied by an editable grid-emissions factor |
| AI | Optional server-side OpenAI-compatible chat proxy, configured for Groq by default |

## Run locally

Requirements: Python 3.9 or newer and a modern browser.

```bash
git clone git@github.com:rohanmalhotracodes/roofgrid.git
cd roofgrid
cp .env.example .env.local
python3 server_local.py
```

Open <http://localhost:8000>. Use `server_local.py` rather than opening the HTML files directly because RoofGrid's AI, OpenStreetMap, contact, and NASA requests use private proxy routes.

### Environment variables

Only the relevant private values need to be added to `.env.local`:

```dotenv
GROQ_API_KEY=gsk_your_real_key
CONTACT_EMAIL=you@example.com
```

`GROQ_API_KEY` enables AI chat. `CONTACT_EMAIL` routes contact-form messages through FormSubmit; the recipient may need to confirm FormSubmit's one-time activation email. Provider, model, and other optional AI settings are documented in `.env.example`.

Never put real credentials in `.env.example`, frontend JavaScript, or any committed file. Restart the local server after changing `.env.local`.

## Deploy to Vercel

1. Import this repository into Vercel and select the **Other** framework preset.
2. Leave the build, output, and install commands empty; `vercel.json` contains the required routes.
3. Add `GROQ_API_KEY` and `CONTACT_EMAIL` under **Production and Preview** environment variables.
4. Add any optional AI provider or model variables described in `.env.example`.
5. Deploy again after adding or changing environment variables.

Keep these variables server-side. Do not prefix them with `NEXT_PUBLIC_` or expose them in browser code.

## Deploy to AWS

The AWS deployment runs the static site on **Amplify Hosting** and the existing `/api/*` routes on **API Gateway + Lambda**. Amplify uses Amazon S3 and CloudFront behind the scenes, while Lambda logs are available in CloudWatch. This is an additional deployment path; it does not change or disable the Vercel deployment.

### 1. Store the private settings

In AWS Secrets Manager, create one secret containing this JSON:

```json
{
  "GROQ_API_KEY": "gsk_your_real_key",
  "CONTACT_EMAIL": "you@example.com"
}
```

Copy the secret ARN. Never add these values to Amplify environment variables, the repository, or browser code.

### 2. Deploy the API

For the quickest setup, authenticate the AWS CLI and run:

```bash
bash aws/deploy.sh
```

The helper will:

- create or update the `roofgrid/config` Secrets Manager secret;
- build the Lambda package with SAM;
- deploy API Gateway + Lambda through CloudFormation;
- run the `/api/health` check; and
- optionally configure the Amplify `/api/<*>` rewrite when you provide your Amplify app ID.

You can override defaults before running it:

```bash
AWS_REGION=ap-south-1 \
STACK_NAME=roofgrid-api \
ALLOWED_ORIGIN=https://your-amplify-domain.amplifyapp.com \
bash aws/deploy.sh
```

Or deploy manually:

```bash
cd aws
sam build
sam deploy --guided
```

Use a stack name such as `roofgrid-api`, choose your AWS Region, and provide the Secrets Manager ARN when SAM asks for `RoofGridSecretArn`. Keep `AllowedOrigin` as `*` for the first deployment. SAM creates the Lambda function, API Gateway routes, IAM permission for that one secret, and CloudWatch logging. Save the deployment configuration when prompted.

When deployment finishes, copy the `ApiUrl` output. Confirm the API is live by opening:

```text
https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/api/health
```

### 3. Deploy the site with Amplify Hosting

1. In Amplify Hosting, connect this GitHub repository and branch. This project is **not a monorepo**, so leave the monorepo option off.
2. Amplify will read the root `amplify.yml`; no framework preset, frontend build command, or output directory needs to be entered manually.
3. Deploy the branch.
4. Open **Hosting → Rewrites and redirects** and add the reverse proxy below as the first rule:

| Source | Target | Type |
| --- | --- | --- |
| `/api/<*>` | `https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/api/<*>` | `200 (Rewrite)` |

Replace the target host with the `ApiUrl` from SAM. An importable example is available in `aws/amplify-rewrites.example.json`.

The proxy keeps all frontend requests on `/api/ai`, `/api/contact`, `/api/nasa`, and `/api/overpass`, so no application code or public API URL has to be changed. After the Amplify domain is final, redeploy the SAM stack with that origin for `AllowedOrigin` if you want to restrict direct cross-origin API calls.

### Updating the AWS deployment

Amplify rebuilds the frontend after a push to the connected branch. Backend changes are deployed separately:

```bash
cd aws
sam build
sam deploy
```

The AWS and Vercel deployments can remain live at the same time. Vercel continues to use `vercel.json` and the handlers in `api/`; AWS uses `amplify.yml` and `aws/template.yaml`.

## Planning limitations

- Satellite imagery and OpenStreetMap outlines may be incomplete, outdated, or misaligned.
- Production, cost, savings, payback, and emissions results depend on the assumptions entered by the user.
- Shade, structural capacity, electrical design, fire setbacks, permits, tariffs, and equipment availability require local verification.
- AI responses may be inaccurate and do not replace utility guidance, regulations, engineering, or professional advice.

RoofGrid is an exploration and planning tool—not an engineering design, structural assessment, permit set, installer quote, or carbon-accounting product.

## License

RoofGrid is available under the [MIT License](LICENSE).
