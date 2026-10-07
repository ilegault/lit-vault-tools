# Literature Review Vault — Context

Status: design decisions complete (rounds 1–3). Tickets are in `.scratch/lit-vault/issues/`. This file is the spec; there is no separate `spec.md`. Read it fully before touching code.

## Vision

A second Obsidian vault, separate from the coursework vault, dedicated to the PhD literature review (ion beam irradiation / nuclear materials). The point is exploration, not storage: open a paper, see what it cites and what cites it, hover over any of those to read its title, authors and abstract, and follow whichever thread looks promising — a rabbit hole you steer one hop at a time. Only papers Isaac decides to **save** become permanent; everything seen while exploring is temporary.

## Two modes

The system has exactly two jobs, run as two separate commands. Both are run manually — nothing ever runs in the background.

1. **Enrich** (permanent, saved papers only). For every saved paper note, fill in graph metadata: institutions, authors, subfield, and links to *other saved papers* it cites or is cited by. This builds the permanent "library graph". It never creates stubs.
2. **Explore** (temporary, one paper at a time). For one focus paper, fetch its current references and citations fresh from Semantic Scholar and write them as temporary **stub notes** into `_explore/`. Running Explore again on a different paper wipes `_explore/` first. Exploring a stub makes that stub the new focus — this is how the rabbit hole works.

Saving a stub = adding it to Zotero (see Stub lifecycle). That is the only way anything leaves `_explore/` and becomes permanent.

## Existing / planned stack

- **Zotero** holds the PDFs. WebDAV sync to the home Nextcloud box.
- **Better BibTeX** generates stable citekeys.
- **Zotero Integration** (Obsidian plugin) generates one note per saved paper from Zotero. Its template must use a persist block (see Note ownership).
- **The enrichment script** (to build) — one program with two commands, `enrich` and `explore`.
- **Shell commands** (Obsidian plugin) — binds `explore` to a hotkey / command-palette entry that passes the currently open note's path, so exploring never means leaving Obsidian. Still manual (a deliberate keypress), consistent with "nothing runs in the background". Verify the plugin is maintained before relying on it.
- **Page Preview** (core plugin) — hover over a node/link to read a stub's title, authors and abstract.
- **Breadcrumbs** (plugin) — typed `refs` / `cited_by` relationships and the Matrix view.
- **Map View** (plugin) — institution pins.
- **Bases** (core plugin) — table/card views over saved papers by property.

## Note ownership model

Every saved paper note has three owners; each only touches its own region:

1. **Zotero Integration** owns citekey, title, year, DOI, PDF link, abstract — regenerated from Zotero.
2. **The enrichment script** owns a defined set of frontmatter keys (below) — never touches body text or Zotero's fields.
3. **Isaac** owns the note body — **must never be lost**. Zotero Integration overwrites the whole note on re-import by default, so the import template wraps the user section in `{% persist "notes" %} … {% endpersist %}`, which survives re-imports. Test this on one paper during setup before trusting it.

Because Zotero Integration rewrites frontmatter on re-import, enrichment fields are disposable: re-run `enrich` on a note after any import. This is an expected step, not an edge case.

The script never renames, moves or deletes saved paper notes. Its only deletions are inside `_explore/` (wiping old stubs) and retiring a stub once its paper is saved.

## Data sources — decisions and why

- **Semantic Scholar — primary for Explore.** `/paper/DOI:<doi>/references` and `/citations` return titles, authors, year, abstract, tldr, citationCount, externalIds (DOI), isInfluential, contexts, intents — everything a stub needs in one paginated call (`offset`/`limit`, max 1000; `next` absent on the last page; 10 MB response cap — keep the bulk field set lean). Free key → 1 req/s. **Hidden references (confirmed 2026-10-06):** for many paywalled papers (seen on Acta Materialia and J. Mater. Res. papers) the publisher has Semantic Scholar hide the reference list: `/references` answers 200 with `"data": null` and a disclaimer that `references` were elided. Open-access papers (e.g. Materials & Design) are visible; citations are unaffected. Explore then falls back to Crossref (decision 17). The key header `x-api-key` is case-sensitive.
- **OpenAlex — primary for Enrich.** Authors (with OpenAlex author IDs), institutions (ROR, country), subfield, open-access status, reference list (IDs). Institution coordinates need a second, cached lookup per institution (confirmed: the work's institution objects are dehydrated). CC0, so responses can be test fixtures. Free key.
- **Crossref — fallback** when OpenAlex has no record for a DOI. Email in the polite pool. Also the source of reference DOIs for Explore when Semantic Scholar hides a paper's references (decision 17).
- **OSTI.gov — fallback for no-DOI items** (DOE technical reports).
- **Unpaywall — not used.** **TDS extraction pipeline — out of scope**, kept fully separate.

## Saved paper frontmatter (enrichment-owned keys)

```yaml
---
type: paper
citekey: smith2021ion
doi: 10.1016/j.jnucmat.2021.000000     # normalized: lowercase, no URL prefix
# ---- enrichment-script-owned ----
openalex_id: W1234567890
s2_id: 1234abcd                        # Semantic Scholar paper ID
oa_status: green
institutions: ["[[Oak Ridge National Laboratory]]"]
countries: [US]
authors: ["[[Jane Doe]]"]
subfield: ["[[Nuclear Energy and Engineering]]"]
refs: ["[[@jones2019dpa]]"]            # only papers that are ALSO saved
cited_by: ["[[@lee2023foo]]"]          # only papers that are ALSO saved
enrich_status: ok                      # ok | partial | no_doi | not_found | error
enriched_on: 2026-09-26                # changes only when an enrichment field's value changed
---
```

- No citation counts are stored permanently. Counts are fetched fresh at Explore time and shown on stubs, so they're always current when Isaac is actually looking.
- `refs` / `cited_by` link saved papers to saved papers only. Links to unsaved papers exist only temporarily, in Explore mode.
- **Idempotency:** same data in → same file out. Running `enrich` twice with nothing changed upstream leaves files byte-identical (which is why `enriched_on` only moves when something changed).
- Matching between the script and notes is always by `doi` / `openalex_id` / `s2_id` in frontmatter, never by filename.
- No thresholds anywhere: every author of a saved paper gets a node.
- Topics linked at the OpenAlex subfield level only; a hand-curated `themes:` field is Isaac's.

## Authors

Authors are hard because names collide ("J. Smith") and vary ("Jane Doe", "J. A. Doe"). Rules:

- **Identity = OpenAlex author ID**, stored as `openalex_id` in the author note. Never match authors by name.
- **Filename = display name** (readable graph label). If two different author IDs share a display name, the second gets a disambiguator from their institution: `Jane Doe (ORNL)`.
- **`aliases:`** in the author note collects every name variant seen on saved papers, so Obsidian resolves links and search across variants.
- Two notes with different IDs are never merged automatically (OpenAlex sometimes splits one person into two IDs; Isaac can merge by hand).
- Author notes are created for saved papers only. Stubs show authors as plain text — no author nodes for temporary stubs, so exploring never litters the vault.

Institution notes: `type: institution`, `ror`, `country`, `institution_type` (OpenAlex's own type; named so it does not clash with the note-kind `type`), `openalex_id`, `location: lat,lng` (Map View format, confirmed). Omit `location` entirely if unknown — never `0,0`.

## Stub lifecycle (temporary previews)

1. **Explore** a focus paper (hotkey in Obsidian on the open note). `_explore/` is wiped, then one stub per reference and citation is written. The focus note gets temporary `refs`/`cited_by`-style links to them (written in `_explore/_focus.md` rather than in the saved note, so saved notes never carry temporary links — **decided, round 3**).
2. Stub content: title, authors (plain text), year, venue, current citation count, `isInfluential`, tldr, abstract, DOI, and whether it's a reference or a citation. Frontmatter carries `type: stub`, `doi`, `s2_id`.
3. **Stub filenames are readable**, because graph labels are filenames: `Jones 2019 - Dislocation loops in irradiated…` (truncated), with a suffix on collision. Identity is the `s2_id`/`doi` in frontmatter.
4. **Hover** a stub in the local graph or the focus list → Page Preview shows the abstract. Isaac judges relevance without opening anything.
5. **Rabbit hole:** run Explore on a stub → it becomes the focus; `_explore/` is rebuilt around it. **Trail:** the last 3 foci (configurable) are kept. Their own notes survive the wipe (only their neighbours are cleared), and `_explore/_trail.md` lists them in order, newest first, as links. Backing up = run Explore on a trail entry, which re-fetches its neighbours fresh. A trail entry that's a saved paper just links to the real note. The oldest entry drops off (and its stub is deleted) when a 4th focus is added.
6. **Save:** add the stub's DOI to Zotero → Zotero Integration creates the real note → run `enrich` on it. **Stub retirement:** whenever `enrich` or `explore` runs, any stub whose DOI now matches a saved paper is deleted and links point to the real note. Since stubs are temporary anyway, retirement mostly matters for the current `_explore/` session.

**Cap and load more (decided):** each list (references, citations) shows at most **200 stubs** per pass, configurable. Semantic Scholar can't sort citations server-side, so Explore first pages through the whole list with lean fields (ID, title, year, citationCount, isInfluential — cheap, 1000 per call), ranks locally (influential first, then citation count), and writes stubs for the top 200. It then fetches abstracts and tldrs for just those 200 via the batch paper endpoint. **Load more** = re-run Explore on the same focus with a "more" flag. That adds the next 200 from the same ranking without wiping the ones already shown. `_focus.md` shows "showing 200 of 3,412 citations" so it's obvious when there's more.

Stub size stays bounded: at most one focus paper's neighbours (plus the trail's focus notes) exist at a time.

## Graph strategy

- **Explore view = Local Graph, depth 1**, on the focus paper: saved papers + temporary stubs connected to it. Stubs grey via a native Graph Group (`path:_explore`).
- **Library view = Global Graph** with the filter `-path:_explore`: only saved papers, authors, institutions and subfields — the permanent picture of what Isaac has collected.
- **Breadcrumbs Matrix** for references-only / citations-only lists (native graph can't filter by link direction). `refs` and `cited_by` must be registered once under Settings → Breadcrumbs → Edge Fields.
- **Map View** for institution pins. **Bases** for property-based browsing.

## Confirmed facts

1. OpenAlex work → institution objects are dehydrated (no lat/lon); geo needs a cached per-institution lookup.
2. Map View: `location: lat,lng` (array form also accepted), one per note.
3. Breadcrumbs custom edge fields must be registered manually once.
4. Zotero Integration overwrites the whole note on re-import, no merge — hence persist blocks + re-run `enrich`.
5. Semantic Scholar endpoints and fields as listed above, verified against the real `swagger.json`; `DOI:<doi>` is a valid paper ID.
6. Semantic Scholar's API key header is `x-api-key`, case-sensitive (stated in its API docs; confirmed when urllib's re-capitalised header was ignored).
7. Semantic Scholar hides references for many paywalled papers (`"data": null` on `/references`); OpenAlex and Crossref still list them (checked on one Acta Materialia paper: 106 and 100 references). Real response saved as `tests/fixtures/s2_references_elided.json`.

## Decisions — confirmed by Isaac

1. No thresholds on any nodes.
2. Both commands run manually only (hotkey counts as manual). No watcher.
3. One-time Obsidian UI steps live in the setup checklist, not tickets.
4. (Round 2) Zotero must never destroy Isaac's notes → persist block in the import template.
5. (Round 2) Stub retirement system is wanted.
6. (Round 2) No permanently stored citation counts; fetch fresh when exploring.
7. (Round 2) Old author-threshold schema removed; authors identified by OpenAlex ID with collision-safe filenames and aliases.
8. (Round 2) Stubs are temporary previews, scoped to one focus paper at a time; only saved papers are permanent.
9. (Round 2) Explore view centers on the open paper; the global graph shows saved papers only.
10. (Round 2) Explore keeps a short trail: last 3 foci, configurable.
11. (Round 2) Cap of 200 stubs per list per pass, ranked influential-first then by citation count, with "load more".
12. (Round 3, amended 2026-10-06) HTTP uses the Python standard library `http.client` behind an injectable transport function, so the project adds no runtime dependency and tests pass a fake transport that replays saved responses. **Not `urllib`:** it re-capitalises header names, and Semantic Scholar's `x-api-key` header is case-sensitive, so urllib silently sends every request unauthenticated (found while capturing fixtures: constant 429s that PowerShell, which keeps header case, did not get).
13. (Round 3) The institution geo cache is a JSON file outside the vault, so it never syncs to the phone: `%LOCALAPPDATA%\lit-vault-tools\institutions.json` on Windows, else `$XDG_CACHE_HOME/lit-vault-tools/` or `~/.cache/lit-vault-tools/`. Overridable by an `LIT_VAULT_CACHE_DIR` environment variable (tests use this).
14. (Round 3) Temporary links to stubs live only in `_explore/_focus.md`, never in a saved note.
15. (Round 3) Real API responses must be captured into `tests/fixtures/` by the developer (needs the live keys) before any client ticket starts; agents never invent response shapes.
16. (Round 3) Institution notes carry `type: institution`; OpenAlex's institution type is stored as `institution_type`.
17. (2026-10-06) **Reference fallback.** When Semantic Scholar hides a focus paper's references, Explore takes the reference DOIs from Crossref and looks them up with Semantic Scholar's `/paper/batch` (`DOI:` ids, lean fields). Ranking, cap, stubs and load-more work as usual; `isInfluential` is unknown for these, so it is false and ranking falls back to citation count. `_focus.md` says the references came from Crossref and how many DOIs were found. References without a DOI, or unknown to Semantic Scholar, are skipped. If Crossref has nothing either, the references list is empty with a note; citations still show.
18. (2026-10-06) **Semantic Scholar rate limit.** The client spaces requests by `config.S2_MIN_INTERVAL_S` (1.5 s; the nominal 1 req/s proved tight in practice) and retries a 429 with exponential backoff (5, 10, 20, 40 s) before failing.

## Manual setup checklist (once, before first run)

- [ ] Zotero Integration import template wraps the user section in `{% persist "notes" %} … {% endpersist %}`; re-import one test paper and confirm a line typed in the body survives.
- [ ] Better BibTeX installed; citekeys stable.
- [ ] Breadcrumbs: register edge fields `refs` and `cited_by`.
- [ ] Map View installed. Bases and Page Preview core plugins enabled.
- [ ] Shell commands plugin: add `explore` bound to a hotkey, passing the active file path.
- [ ] Graph: Group `path:_explore` coloured grey; global graph filter `-path:_explore` saved.
- [ ] Phone (Remotely Save): ignore `_explore/`.
- [ ] Confirm Page Preview works on hover inside the graph view (may need Ctrl/Cmd+hover).
- [ ] Zotero → WebDAV → Nextcloud working end to end for one paper.

## Explicitly out of scope (for now)

- Experimental-parameter extraction (TDS pipeline).
- Unpaywall.
- Any watcher / auto-run mode.
- Permanent storage of unsaved papers.
