# RegLens — marketing site

A single self-contained landing page that explains what RegLens is and how it works.
No build step, no dependencies — just static HTML with inline CSS, matching the
demo UI's dark theme.

## Preview locally

```bash
# any static server works
python3 -m http.server -d site 8080
# then open http://localhost:8080
```

Or just open `site/index.html` directly in a browser.

## Deploy

Live at **https://manas-rai.github.io/reglens/**.

Deployment is automated via GitHub Pages: `.github/workflows/deploy-pages.yml`
uploads the `site/` directory and publishes on every push to `main` that touches
`site/**` (or on manual `workflow_dispatch`). Pages is configured with the
"GitHub Actions" build source — no branch-based publishing.

It's a single static file, so it also drops into anything else:

- **S3 + CloudFront** — `aws s3 cp site/index.html s3://<bucket>/index.html`
- **Netlify / Vercel / Cloudflare Pages** — set the publish directory to `site`

Update the GitHub link in `index.html` (`https://github.com/manas-rai/reglens`)
if the repo URL changes.
