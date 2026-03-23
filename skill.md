# zotero-notebooklm Skill

Export Zotero collections to Google NotebookLM notebooks. The `list` view shows
Zotero collections side-by-side with their paired NotebookLM notebooks — use it
to resolve fuzzy collection references before running an export or sync.

## When This Skill Activates

- User says "/zotero-notebooklm" or asks to export/sync a Zotero collection to NotebookLM
- User refers to a Zotero collection by a short or ambiguous name (e.g. "DataSci", "Piracy")
- User asks to add new papers from Zotero to an existing NotebookLM notebook
- User asks to create a NotebookLM notebook from a Zotero collection

## Prerequisites

1. `zotero-notebooklm` installed (`pip install zotero-notebooklm` or from source)
2. Credentials configured (`zotero-notebooklm config` or `~/.zotero_notebooklm/.env`)
3. NotebookLM authenticated (`notebooklm login`)

## Resolving Fuzzy Collection References

When the user refers to a collection by a short or ambiguous name, ALWAYS run
`zotero-notebooklm` (no arguments) first. The output shows:

```
ZOTERO COLLECTION               NOTEBOOKLM NOTEBOOK                   NOTEBOOK ID
Data Science Methods            Zotero: Data Science Methods          d2072bd5...
Piracy                          Zotero: Piracy                        e0333cde...
Macro                           (no notebook yet)
```

Use this to confirm which collection the user means, and whether a paired
notebook already exists before deciding to export or sync.

## Quick Reference

| Task | Command |
|------|---------|
| List collections + paired notebooks | `zotero-notebooklm` |
| Export collection → new notebook | `zotero-notebooklm "Collection Name"` |
| Add only new papers to existing notebook | `zotero-notebooklm "Collection Name" --sync` |
| Target a specific notebook by ID | `zotero-notebooklm "Collection Name" --notebook <id>` |
| Override local storage path | `zotero-notebooklm "Collection Name" --zotero-dir /path` |
| Set up credentials | `zotero-notebooklm config` |
| Install Claude skill | `zotero-notebooklm skill install` |

## Sync Behaviour

`--sync` automatically:
1. Finds the paired `Zotero: <collection>` notebook by name
2. Compares existing NotebookLM sources against Zotero PDFs by title
3. Uploads only papers not already present
4. Reports how many were skipped vs added

## Credential Lookup Order

1. Environment variables (`ZOTERO_LIBRARY_ID`, `ZOTERO_API_KEY`)
2. `.env` in the current directory
3. `~/.zotero_notebooklm/.env` (global config)

## Autonomy Rules

**Run automatically:**
- `zotero-notebooklm` (list collections + notebooks — use to resolve ambiguous names)
- `zotero-notebooklm "Name"` (export)
- `zotero-notebooklm "Name" --sync` (sync)
- `zotero-notebooklm skill install`

**Ask before running:**
- `zotero-notebooklm config` — writes credentials to disk

## Behaviour Notes

- PDFs are named by paper title so NotebookLM displays the full title as the source name
- Notebook is named `Zotero: <collection name>` for easy pairing
- `--sync` compares by normalised title (case-insensitive, ignores `.pdf` extension)
- Cloud-synced libraries: downloaded via Zotero API
- Local-only: falls back to `Zotero/storage/<key>/` or `--zotero-dir`
- Linked files resolved from the stored path in Zotero metadata
