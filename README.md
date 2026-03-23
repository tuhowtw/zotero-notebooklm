# zotero-notebooklm

Export Zotero collections to Google NotebookLM notebooks. PDFs are uploaded with the paper title as the source name, and a new NotebookLM notebook is created per collection.

## Features

- Exports an entire Zotero collection to a NotebookLM notebook in one command
- Sources named by paper title (not filename)
- Works from any directory via global credentials
- Supports cloud-synced and locally stored Zotero libraries
- Installs as a Claude Code skill (`/zotero-notebooklm`)

## Requirements

- Python 3.9+
- [notebooklm-py](https://github.com/teng-lin/notebooklm-py) installed and authenticated
- A Zotero account with API access

## Installation

```bash
pip install zotero-notebooklm
```

Or from source:

```bash
git clone https://github.com/YOUR_USERNAME/zotero-notebooklm
cd zotero-notebooklm
pip install -e .
```

## Setup

### Step 1 — Get your Zotero credentials

Go to [zotero.org/settings/keys](https://www.zotero.org/settings/keys):

- **Library ID**: the numeric "Your userID" shown at the top of the page
- **API Key**: click "Create new private key", enable **Read Only** library access, save

### Step 2 — Configure credentials

Run the interactive setup (saves to `~/.zotero_notebooklm/.env`, readable only by you):

```bash
zotero-notebooklm config
```

Or create the file manually:

```bash
# ~/.zotero_notebooklm/.env
ZOTERO_LIBRARY_ID=1234567
ZOTERO_API_KEY=yourApiKeyHere
ZOTERO_LIBRARY_TYPE=user
```

> **Security:** credentials are stored in `~/.zotero_notebooklm/.env` with `600` permissions (owner read/write only). This file is never committed — `.gitignore` excludes all `.env` files.

You can also use a local `.env` file in any project directory. Lookup order:
1. Shell environment variables
2. `.env` in the current directory
3. `~/.zotero_notebooklm/.env` (global fallback)

### Step 3 — Authenticate NotebookLM

```bash
notebooklm login
notebooklm status   # verify
```

## Usage

```bash
# List all Zotero collections
zotero-notebooklm

# Export a collection to a new NotebookLM notebook
zotero-notebooklm "My Collection"

# Partial name match also works
zotero-notebooklm "Piracy"

# Add to an existing NotebookLM notebook
zotero-notebooklm "My Collection" --notebook <notebook-id>

# Override the local Zotero storage path (for local-only libraries)
zotero-notebooklm "My Collection" --zotero-dir "C:\Users\You\Zotero\storage"
```

The resulting NotebookLM notebook is named `Zotero: <collection name>`.

### Local vs. cloud storage

| Setup | Behavior |
|-------|----------|
| Zotero cloud sync (default) | PDFs downloaded via Zotero API |
| Local storage only | Falls back to `Zotero/storage/<key>/` on disk |
| Linked files | Resolved from the path stored in Zotero metadata |

If your Zotero data folder is not in the default location, set `ZOTERO_DATA_DIR` in your `.env`:

```
ZOTERO_DATA_DIR=D:\My Documents\Zotero\storage
```

## Claude Code Skill

Install as a Claude Code skill so you can ask Claude to export collections naturally:

```bash
zotero-notebooklm skill install
```

After installing, Claude Code will understand requests like:
- *"Export my Creative Industry Econ collection to NotebookLM"*
- *"Create a notebook from my Zotero Economics collection"*

## Credential Safety Summary

| What | Where | Committed? |
|------|-------|-----------|
| Global credentials | `~/.zotero_notebooklm/.env` | No — outside repo |
| Local credentials | `./.env` | No — in `.gitignore` |
| Example template | `.env.example` | Yes — no real values |

Never put real credentials in `.env.example` or any tracked file.

## License

MIT
