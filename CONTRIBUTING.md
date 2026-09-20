# Contributing to RoofGrid

Thank you for your interest in contributing to RoofGrid! Contributions that improve the rooftop solar planning experience, fix bugs, enhance accessibility, improve documentation, or strengthen the project's reliability are welcome.

Please read this guide before opening an issue or submitting a pull request.

## Getting started

### 1. Find an issue

Browse the [open issues](https://github.com/rohanmalhotracodes/roofgrid/issues) to find something you would like to work on.

Before starting:

* Check whether an issue or pull request already addresses the same problem.
* Read the issue description and any existing discussion.
* Comment on the issue to express your interest and clarify the expected scope.
* For substantial changes or new features, discuss your proposed approach with the maintainers before implementing it.

If you discover a bug or have a feature suggestion, open a new issue with a clear description.

### 2. Fork and clone the repository

Fork [RoofGrid](https://github.com/rohanmalhotracodes/roofgrid) to your GitHub account.

Clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/roofgrid.git
cd roofgrid
```

Add the original repository as an upstream remote:

```bash
git remote add upstream https://github.com/rohanmalhotracodes/roofgrid.git
```

Replace `YOUR_USERNAME` with your GitHub username.

### 3. Set up the project locally

Requirements:

* Python 3.9 or newer
* Git
* A modern web browser

Create your local environment configuration:

```bash
cp .env.example .env.local
```

Start the local development server:

```bash
python3 server_local.py
```

Open http://localhost:8000 in your browser.

Use the local server rather than opening HTML files directly because some features depend on backend proxy routes.

The main frontend pages are `index.html`, `solar_advanced.html`, and `privacy.html`. Local backend functionality is provided by `server_local.py`, with additional API and AWS deployment code in `api/` and `aws/`.

### Environment variables

Some optional features require private configuration values in `.env.local`.

For example:

```dotenv
GROQ_API_KEY=your_api_key
CONTACT_EMAIL=you@example.com
```

You do not need an AI API key for every frontend or documentation contribution.

**Never commit API keys, credentials, `.env.local`, or other private information.** Use `.env.example` only for safe placeholders and documented configuration names.

See the [README](README.md) for additional setup and deployment details.

## Making changes

### 1. Create a branch

Before beginning your work, update your local `main` branch:

```bash
git switch main
git pull --ff-only upstream main
```

Create a descriptive branch for your change:

```bash
git switch -c fix/short-description
```

Other suitable prefixes include `feat/`, `docs/`, and `refactor/`.

Keep each branch focused on one issue or closely related set of changes.

### 2. Follow the existing project conventions

* Keep changes small, focused, and easy to review.
* Follow the formatting and naming conventions already used in the files you modify.
* Avoid unrelated refactoring or formatting changes.
* Preserve responsive layouts, accessibility, and existing functionality when modifying the frontend.
* Do not expose credentials or move private server-side configuration into browser code.
* Update documentation when your change affects setup instructions, configuration, or user-facing behavior.

### 3. Test your changes

Run the project locally and verify the behavior affected by your changes.

Depending on the contribution, this may include:

* Checking modified pages in a browser at desktop and mobile viewport sizes.
* Verifying navigation, links, forms, and keyboard accessibility.
* Checking the browser console for errors.
* Testing relevant backend routes or API behavior.
* Confirming that documentation commands and links are accurate.

Before committing, check for whitespace errors:

```bash
git diff --check
```

Review the complete diff:

```bash
git diff
```

If automated tests are available for the area you changed, run the relevant tests and include the results in your pull request.

Do not claim that a check passed unless you actually ran it.

## Commit your changes

Stage only the files related to your contribution:

```bash
git add path/to/changed-file
```

Create a concise, descriptive commit:

```bash
git commit -m "fix: describe the issue being resolved"
```

Use a suitable prefix such as `fix:`, `feat:`, `docs:`, or `refactor:` to make the commit history easier to follow.

Avoid including unrelated changes in the same commit.

## Submit a pull request

Push your branch to your fork:

```bash
git push -u origin HEAD
```

Open a pull request from your fork's branch into the original RoofGrid repository's `main` branch.

In your pull request:

* Explain what changed and why.
* Link the relevant issue.
* Summarize how you tested the changes and report the results.
* Include screenshots or recordings for visible UI changes when useful.
* Mention known limitations or follow-up work.

If your pull request fully resolves an issue, include a closing keyword in its description:

```text
Closes #123
```

Replace `123` with the actual issue number. If your pull request only partially addresses an issue, use:

```text
Related to #123
```

Complete the repository's pull request template when one is available.

## Review process

Maintainers may request changes or clarification during review. Please respond to feedback and update the same branch so the pull request stays easy to follow.

Do not open a duplicate pull request for revisions to an existing one.

A pull request is not considered merged until the maintainers approve and merge it.

## Reporting bugs and suggesting features

When opening an issue, provide enough information for others to understand and reproduce the problem.

For bug reports, include:

* A clear description of the unexpected behavior.
* Steps to reproduce the problem.
* Expected and actual results.
* Relevant browser, operating system, and environment details.
* Screenshots or error messages, with sensitive information removed.

For feature requests, describe the problem you want to solve, the proposed behavior, and any relevant alternatives.

## License

By contributing, you agree that your contributions will be made available under the project's [MIT License](LICENSE). Ensure that you have the right to submit any code, documentation, images, or other materials included in your contribution.

Thank you for helping improve RoofGrid!
