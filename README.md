# Research Paper API

A minimal FastAPI backend accompanied by a local GROBID service for parsing
research-paper PDFs into structured TEI XML, plus a Vite React frontend using
TanStack Router file-based routing and Tailwind CSS.

## Start the stack

Docker and the Docker Compose plugin are required. From this directory, run:

```bash
docker compose up --build
```

The first run downloads the GROBID CRF image, so it can take a few minutes.
Once both containers are ready:

- FastAPI hello route: <http://rig:3333/hello>
- PDF parsing route: `POST http://rig:3333/papers/parse`
- Interactive API docs: <http://rig:3333/docs>

Verify the API:

```bash
curl http://rig:3333/hello
```

Expected response:

```json
{"message":"Hello, World!"}
```

Upload a paper through FastAPI and save the returned TEI XML:

```bash
curl --form file=@sample_papers/attention-is-all-you-need.pdf \
  http://rig:3333/papers/parse \
  --output paper.tei.xml
```

The endpoint accepts PDFs up to 50 MB, forwards them to GROBID's full-document
parser, and returns the resulting TEI XML as a download. The API container
reaches GROBID at the internal `http://grobid:8070` address configured through
the `GROBID_URL` environment variable.

### Normalize TEI into Paper JSON

Convert an existing GROBID TEI file into the internal Paper AST:

```bash
curl --form file=@paper.tei.xml \
  http://rig:3333/papers/normalize \
  --output paper.json
```

Or run the complete PDF → GROBID → Paper JSON pipeline in one request:

```bash
curl --form file=@sample_papers/bert.pdf \
  http://rig:3333/papers/parse/json \
  --output paper.json
```

The JSON preserves sections and paragraph-level text/citation nodes. Adjacent
GROBID citation fragments are grouped into a single citation node with their
`referenceIds`. Any targetless GROBID citation fragments remain visible in
`unresolvedFragments`; IDs targeting a missing bibliography entry are reported
in the paper's `unresolvedReferenceIds`.

Every bibliography entry is retained with its original `rawText`, extracted
`rawFields`, and a canonical CSL-JSON `csl` object. Reference status is:

- `parsed` when title, author, and issued date were all extracted
- `partial` when some structured CSL data exists but core fields are missing
- `failed` when GROBID supplied no usable structured fields (`csl` is `null`)

### Look up references on OpenAlex

After parse, send the Paper JSON to OpenAlex. Each bibliography entry is
matched by DOI, then arXiv id, then title+year. Misses stay `unmatched`;
nothing is invented.

```bash
curl --header 'Content-Type: application/json' \
  --data @paper.json \
  http://rig:3333/papers/enrich \
  --output paper.enriched.json
```

Each reference gains `openalex`, `openalexStatus` (`matched`, `unmatched`,
`error`, or `skipped`), and `openalexError` when lookup failed. Successful
lookups are cached in `/data/openalex-cache.jsonl` so repeats do not spend
OpenAlex quota. Set `OPENALEX_MAILTO` in `.env` to use the polite pool, and
`OPENALEX_PROXY` if you want requests to leave through your own proxy.

### Find missing related work

After parse (and preferably after OpenAlex enrichment), search for papers the
bibliography does not already contain:

```bash
curl --header 'Content-Type: application/json' \
  --data @paper.json \
  http://rig:3333/papers/missing-works \
  --output missing-works.json
```

The API extracts a few claim-like sentences from Introduction / Related Work,
searches OpenAlex, and drops anything already cited by DOI, arXiv id, OpenAlex
id, or title. Empty or failed searches are returned as-is. No invented papers.

## Networking

FastAPI is published only on this machine's Tailscale address, configured by
`TAILSCALE_IP` and `API_PORT` in `.env`. With Tailscale MagicDNS enabled, other
devices in the tailnet can access it at `http://rig:3333`; it is not bound to
the machine's LAN or public interfaces. Port `3333` is used because this host
already has another application listening on port `8000`.

GROBID has no host port. It is attached only to Compose's internal `backend`
network and is reachable from FastAPI at `http://grobid:8070`. If the machine's
Tailscale address changes, run `tailscale ip -4`, update `.env`, and recreate
the stack.

## Sample research papers

The `sample_papers` directory contains three open-access arXiv papers that can
be used to exercise the endpoint:

- `attention-is-all-you-need.pdf` — Vaswani et al., 2017
- `bert.pdf` — Devlin et al., 2018
- `language-models-are-few-shot-learners.pdf` — Brown et al., 2020

Try any of them using the cURL command above or the upload form in the
interactive API documentation.

## Frontend development

The React app lives in `frontend/`. Its Vite server listens only on SSH-local
`127.0.0.1:5555` and proxies `/api` calls to the Tailscale-bound FastAPI service.

```bash
cd frontend
bun install
bun run dev
```

Use SSH port forwarding if you want to view it from your computer without
publishing another service:

```bash
ssh -L 5555:127.0.0.1:5555 rig
```

Then open <http://localhost:5555>. Routes are defined under
`frontend/src/routes`; TanStack Router generates the route tree during dev and
build.

## GROBID image choice

The Compose stack uses `grobid/grobid:0.9.0-crf`, the smaller CPU-only image,
which is a convenient development default. For higher extraction accuracy,
especially around citations and references, change it to
`grobid/grobid:0.9.0-full`. The full image is much larger and works best with
a supported GPU.
