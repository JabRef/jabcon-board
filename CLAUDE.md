# JabCon board

Static wall display: `site/` (plain HTML/CSS/JS), `scripts/collect.py` (data, Python stdlib), GitHub Actions publish
to `gh-pages`. No build step. Push to `main` deploys.

## Requirements first

`docs/requirements.md` lists what the board promises (OpenFastTrace `req~name~1` items); the code carries
`[impl->req~name~1]` tags next to the implementation. Before changing code:

1. Read the tags in the functions and CSS rules you touch and the requirements they point to. Each is a promise
   somebody relied on; re-check it after the change (screenshot, or click through) instead of assuming it still holds.
   Typical breakage: a new CSS rule re-anchors a `position: fixed` element, a new overlay is not hidden by default,
   a renamed id changes a selector's meaning.
2. New feature or behaviour change: add or bump a requirement, tag the implementation, keep the description honest.
3. Run `scripts/trace.sh -v failures` (CI does too). It only proves every requirement still has a tag, not that the
   behaviour works; that check is step 1.

Also syntax-check the JS before committing: `node -e "new Function(require('fs').readFileSync('site/app.js','utf8'))"`.

## Verify what you push

A local screenshot of the state you just built is not enough; load the page fresh and look at the default state too.
Push first, fix up after is fine (users see features early), but state the deployed short SHA after every push.

## Data

`data.json` is public. Repos in `private_repos` contribute counts only, never titles or numbers.
