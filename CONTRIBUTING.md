# Contributing to RoofGrid

Thank you for helping improve RoofGrid. Contributions of all sizes are welcome, from documentation corrections to new planning features.

## Before you start

- Search the [open issues](https://github.com/rohanmalhotracodes/roofgrid/issues) to avoid duplicate work.
- For a bug, include clear reproduction steps and your browser or operating-system details.
- For a larger feature or architectural change, open an issue before implementation so the approach can be discussed.
- Never commit API keys, email addresses, credentials, or values from `.env.local`.

## Local setup

RoofGrid requires Python 3.9 or newer and a modern browser.

```bash
git clone https://github.com/<your-username>/roofgrid.git
cd roofgrid
cp .env.example .env.local
python3 server_local.py
```

Open <http://localhost:8000>. The application should be served through `server_local.py`; opening the HTML files directly bypasses the local API proxy routes.

The optional AI assistant requires `GROQ_API_KEY` in `.env.local`. Contact-form delivery requires `CONTACT_EMAIL`. Most layout, mapping, energy, and financial features can be tested without either value.

## Development workflow

1. Fork the repository and create a focused branch from the latest `main`:

   ```bash
   git switch main
   git pull --ff-only upstream main
   git switch -c fix/short-description
   ```

2. Make one logical change per branch. Avoid unrelated formatting or refactors.
3. Test the affected workflow locally at desktop and mobile widths.
4. Update documentation and screenshots when user-visible behavior changes.
5. Commit with a short, imperative message, for example `Fix panel spacing validation`.
6. Push the branch to your fork and open a pull request against `main`.

## Validation checklist

Run the checks relevant to your change before opening a pull request:

- Start `python3 server_local.py` and confirm the page loads without console errors.
- Exercise the modified path from start to finish.
- Verify keyboard navigation, visible focus, labels, and meaningful alternative text for UI changes.
- Check the layout at desktop and mobile widths.
- Confirm that no credentials, generated secrets, or local environment files are staged.
- For backend changes, call the affected `/api/*` endpoint and cover both successful and invalid input.
- For AWS changes, validate the SAM template and document any new configuration or permissions.

## Pull requests

A good pull request:

- explains the problem and the chosen solution;
- links the issue with `Closes #<issue-number>` when appropriate;
- lists the verification performed;
- includes before-and-after images for visible changes; and
- stays small enough to review as one coherent change.

Maintainers may request changes before merging. Please keep review discussion focused and update the same branch rather than opening a replacement pull request.

## Reporting security issues

Do not disclose a suspected vulnerability in a public issue. Contact the repository maintainers privately with reproduction details and the potential impact.

By participating, you agree to keep discussions respectful, constructive, and focused on improving the project.
