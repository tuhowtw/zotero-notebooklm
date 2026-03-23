# zotero-notebooklm Skill

Export Zotero collections to Google NotebookLM notebooks via the `zotero-notebooklm` CLI.

## When This Skill Activates

- User says "/zotero-notebooklm" or asks to export a Zotero collection to NotebookLM
- User asks to sync Zotero papers with NotebookLM
- User asks to create a NotebookLM notebook from a Zotero collection

## Prerequisites

1. `zotero-notebooklm` installed (`pip install zotero-notebooklm` or from source)
2. Credentials configured (`zotero-notebooklm config` or `~/.zotero_notebooklm/.env`)
3. NotebookLM authenticated (`notebooklm login`)

## Quick Reference

| Task | Command |
|------|---------|
| List collections | `zotero-notebooklm` |
| Export collection | `zotero-notebooklm "Collection Name"` |
| Add to existing notebook | `zotero-notebooklm "Collection Name" --notebook <id>` |
| Override storage path | `zotero-notebooklm "Collection Name" --zotero-dir /path` |
| Set up credentials | `zotero-notebooklm config` |
| Install Claude skill | `zotero-notebooklm skill install` |

## Credential Lookup Order

1. Environment variables (`ZOTERO_LIBRARY_ID`, `ZOTERO_API_KEY`)
2. `.env` in the current directory
3. `~/.zotero_notebooklm/.env` (global config)

## Autonomy Rules

**Run automatically:**
- `zotero-notebooklm` (list collections)
- `zotero-notebooklm "Name"` (export — creates notebook and uploads PDFs)
- `zotero-notebooklm skill install`

**Ask before running:**
- `zotero-notebooklm config` — writes credentials to disk

## Behavior Notes

- PDFs are named after the paper title so NotebookLM displays the full title as the source name
- For cloud-synced Zotero libraries: downloads via API
- For local-only files: falls back to `~/.zotero_notebooklm` storage or `--zotero-dir`
- Linked files (stored outside Zotero's folder) are resolved from the stored path
- NotebookLM notebook is named `Zotero: <collection name>`
