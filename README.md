# Signal / Daily — AI & Tech Briefing

A source-linked daily archive of global AI and technology developments, published as plain-text files and presented through a searchable, date-selectable GitHub Pages website.

## Open the briefing site

**Website:** [Open Signal / Daily](https://aniketsinha05.github.io/ai-tech-briefing/)

If Pages has not finished its first deployment yet, wait for the **Deploy AI Tech Briefing Pages** workflow to complete under the repository's Actions tab, then refresh.

## What you get

- **Daily archive:** choose any published coverage date from the date selector.
- **Search:** filter the selected day's stories by topic, title, source, or summary.
- **Source preview cards:** see a publisher, headline and description when a source website exposes preview metadata; open the original article in a new tab.
- **Plain-text originals:** every briefing remains available in the repository for transparency and portability.
- **Automatic site updates:** every push to `main` runs the GitHub Actions workflow to rebuild and deploy the site.

## Briefing files

Daily files are stored by year and month:

```text
ai-tech-briefing/
└── 2026/
    └── 10/
        └── 2026-10-28.txt
```

The filename uses the coverage date, not the date the briefing was prepared. Coverage follows the previous calendar day in India Standard Time (IST).

## How the website works

The site is a static HTML/CSS/JavaScript app. On each push to `main`, GitHub Actions runs `scripts/build_site.py`, reads the dated text files, extracts stories and source URLs, and generates `dist/briefings.json`. For source preview cards, the build attempts to read the public page's Open Graph, Twitter Card, and description metadata. If a publisher blocks requests or provides no metadata, the site still shows a clean fallback card with the source domain and clickable link.

The workflow then deploys the generated `dist/` directory to GitHub Pages. No database or frontend framework is required.

## Topics covered

- AI models, product releases and research
- AI policy, government and regulation
- Developer tools and open source
- Cybersecurity incidents and scams
- Technology companies, partnerships and funding
- Summits, conferences and major industry events

Stories should include concise context and links to the original reporting or announcement. Publisher preview metadata is for convenience; open the source link to read the full article and verify important claims.

## Repository layout

```text
.
├── .github/workflows/pages.yml  # Build and deploy on every push to main
├── ai-tech-briefing/YYYY/MM/    # Dated .txt briefing archive
├── scripts/build_site.py        # Parses briefings and creates preview metadata
├── site/
│   ├── index.html               # Website structure
│   ├── styles.css               # Responsive visual design
│   └── app.js                   # Date picker, search, story and source cards
└── README.md
```

## GitHub Pages setup

The repository's Pages deployment source should be set to **GitHub Actions**. The workflow uses the minimal deployment permissions it needs:

- `contents: read`
- `pages: write`
- `id-token: write`

If the first deployment fails, open **Actions → Deploy AI Tech Briefing Pages** and inspect the failed step. Check **Settings → Pages** and ensure the source is set to GitHub Actions. The site is public because this repository is public.

## Local preview

Requires Python 3.10+ and an internet connection if you want publisher preview metadata to be fetched.

```bash
python scripts/build_site.py
python -m http.server 8000 --directory dist
```

Then open [http://localhost:8000](http://localhost:8000).

## Notes

- Search filters stories for the selected date; it does not currently search across every date at once.
- Publisher preview availability varies. Some sites block automated requests, omit metadata, or require JavaScript; source links remain available in those cases.
- The site displays the briefings committed to this repository. It does not independently guarantee that every news item is accurate; consult linked sources for context and verification.
