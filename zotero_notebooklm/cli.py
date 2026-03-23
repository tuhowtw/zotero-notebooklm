"""
zotero-notebooklm

Export PDFs from a Zotero collection to a Google NotebookLM notebook.

Usage:
    zotero-notebooklm                          # list collections paired with notebooks
    zotero-notebooklm "Collection Name"        # export collection → new notebook
    zotero-notebooklm "Collection Name" --sync # add only new papers to existing notebook
    zotero-notebooklm "Collection Name" --notebook <id>  # target a specific notebook
    zotero-notebooklm --zotero-dir /path       # override local storage path
    zotero-notebooklm skill install            # install Claude Code skill
    zotero-notebooklm config                   # set up global credentials

Credentials are read from (in priority order):
  1. Environment variables
  2. .env in the current directory
  3. ~/.zotero_notebooklm/.env  (global config)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from pyzotero import zotero

GLOBAL_CONFIG_DIR = Path.home() / ".zotero_notebooklm"
SKILL_DEST = Path.home() / ".claude" / "skills" / "zotero-notebooklm.md"
SKILL_SRC = Path(__file__).parent.parent / "skill.md"

NOTEBOOK_PREFIX = "Zotero: "


# ---------------------------------------------------------------------------
# Zotero helpers
# ---------------------------------------------------------------------------

def get_zotero_client():
    library_id = os.environ.get("ZOTERO_LIBRARY_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")

    if not library_id or not api_key:
        config_path = GLOBAL_CONFIG_DIR / ".env"
        print("Error: ZOTERO_LIBRARY_ID and ZOTERO_API_KEY are not set.")
        print(f"Add them to {config_path} or a local .env file.")
        print("Run 'zotero-notebooklm config' to create the global config.")
        sys.exit(1)

    return zotero.Zotero(library_id, library_type, api_key)


def get_all_collections(zot):
    return sorted(zot.collections(), key=lambda c: c["data"]["name"].lower())


def find_collection(zot, name):
    collections = zot.collections()
    name_lower = name.lower()
    matches = [c for c in collections if c["data"]["name"].lower() == name_lower]
    if not matches:
        matches = [c for c in collections if name_lower in c["data"]["name"].lower()]
    if not matches:
        print(f"Error: No Zotero collection matching '{name}' found.")
        print("Run without arguments to list all collections and notebooks.")
        sys.exit(1)
    if len(matches) > 1:
        print(f"Ambiguous name '{name}'. Matching Zotero collections:")
        for m in matches:
            print(f"  {m['key']}  {m['data']['name']}")
        sys.exit(1)
    return matches[0]


def get_pdf_attachments(zot, collection_key):
    """Return list of (item_key, display_title, link_mode, local_path) for all PDFs."""
    items = zot.collection_items(collection_key, itemType="attachment")
    pdfs = []
    for item in items:
        data = item.get("data", {})
        if data.get("contentType") != "application/pdf":
            continue
        parent_key = data.get("parentItem")
        display_title = ""
        if parent_key:
            try:
                parent = zot.item(parent_key)
                display_title = parent["data"].get("title", "")
            except Exception:
                pass
        if not display_title:
            display_title = data.get("title") or data.get("filename") or item["key"]

        link_mode = data.get("linkMode", "")
        local_path = data.get("path", "")
        pdfs.append((item["key"], display_title, link_mode, local_path))
    return pdfs


# ---------------------------------------------------------------------------
# NotebookLM helpers
# ---------------------------------------------------------------------------

def notebooklm(*args):
    result = subprocess.run(["notebooklm", *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_all_notebooks():
    """Return list of {id, title} dicts from NotebookLM."""
    rc, out, _ = notebooklm("list", "--json")
    if rc != 0:
        return []
    try:
        return json.loads(out).get("notebooks", [])
    except json.JSONDecodeError:
        return []


def find_paired_notebook(col_name, notebooks=None):
    """Find a NotebookLM notebook named 'Zotero: <col_name>'. Returns notebook dict or None."""
    if notebooks is None:
        notebooks = get_all_notebooks()
    target = (NOTEBOOK_PREFIX + col_name).lower()
    for nb in notebooks:
        if nb["title"].lower() == target:
            return nb
    return None


def get_notebook_source_titles(notebook_id):
    """Return set of normalised source titles already in a NotebookLM notebook."""
    rc, out, _ = notebooklm("source", "list", "--json", "--notebook", notebook_id)
    if rc != 0:
        return set()
    try:
        sources = json.loads(out).get("sources", [])
        return {_normalise_title(s["title"]) for s in sources}
    except json.JSONDecodeError:
        return set()


def _normalise_title(title):
    """Strip extension and normalise whitespace/case for comparison."""
    t = title.lower().strip()
    if t.endswith(".pdf"):
        t = t[:-4]
    return " ".join(t.split())


def create_notebook(col_name):
    """Create a new NotebookLM notebook named 'Zotero: <col_name>'. Returns notebook id."""
    notebook_title = NOTEBOOK_PREFIX + col_name
    print(f"Creating NotebookLM notebook: '{notebook_title}'...")
    rc, out, err = notebooklm("create", notebook_title, "--json")
    if rc != 0:
        print(f"Error creating notebook: {err}")
        sys.exit(1)
    try:
        notebook_id = json.loads(out)["notebook"]["id"]
        notebooklm("use", notebook_id)
        print(f"Notebook created: {notebook_id}")
        return notebook_id
    except (json.JSONDecodeError, KeyError):
        print("Notebook created (could not parse ID).")
        return None


# ---------------------------------------------------------------------------
# Local storage helpers
# ---------------------------------------------------------------------------

def get_default_zotero_storage_dir():
    """Return the Zotero storage directory, trying known locations in order."""
    candidates = [
        Path.home() / "Zotero" / "storage",  # current default (Zotero 7+)
    ]
    if sys.platform == "win32":
        candidates.append(
            Path(os.environ.get("APPDATA", "")) / "Zotero" / "Zotero" / "storage"
        )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]  # return preferred default even if not found


def find_local_pdf(item_key, storage_dir):
    item_dir = Path(storage_dir) / item_key
    if item_dir.exists():
        pdfs = list(item_dir.glob("*.pdf"))
        if pdfs:
            return str(pdfs[0])
    return None


def resolve_linked_path(raw_path, storage_dir):
    if raw_path.startswith("attachments:"):
        relative = raw_path[len("attachments:"):]
        candidate = Path(storage_dir).parent / relative
        if candidate.exists():
            return str(candidate)
        if Path(relative).exists():
            return str(Path(relative))
        return None
    candidate = Path(raw_path)
    return str(candidate) if candidate.exists() else None


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def sanitize_filename(title):
    safe = "".join(c if c.isalnum() or c in " ,-_()" else " " for c in title)
    safe = " ".join(safe.split())
    return (safe[:100] + ".pdf").strip()


def download_pdf(zot, item_key, title, link_mode, local_path, dest_dir, storage_dir):
    """
    Obtain a PDF named after the paper title (so NotebookLM shows the title).
    Priority: linked path → API download → local storage fallback.
    """
    dest = Path(dest_dir) / sanitize_filename(title)

    if link_mode == "linked_file" and local_path:
        resolved = resolve_linked_path(local_path, storage_dir or "")
        if resolved:
            shutil.copy2(resolved, dest)
            return str(dest)
        print(f"    Warning: linked file not found at '{local_path}'")
        return None

    try:
        content = zot.file(item_key)
        dest.write_bytes(content)
        return str(dest)
    except Exception as api_err:
        print(f"    API download failed ({api_err}), trying local storage...")

    if storage_dir:
        local = find_local_pdf(item_key, storage_dir)
        if local:
            shutil.copy2(local, dest)
            return str(dest)

    print(f"    Warning: could not obtain PDF for {item_key}")
    return None


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(zot):
    """Show Zotero collections paired with their NotebookLM notebooks."""
    collections = get_all_collections(zot)
    notebooks = get_all_notebooks()

    # Index notebooks by normalised title for quick lookup
    nb_by_title = {nb["title"].lower(): nb for nb in notebooks}

    COL_W, NB_W = 30, 36
    print(f"\n{'ZOTERO COLLECTION':<{COL_W}}  {'NOTEBOOKLM NOTEBOOK':<{NB_W}}  NOTEBOOK ID")
    print("-" * (COL_W + NB_W + 40))

    for col in collections:
        col_name = col["data"]["name"]
        paired_title = (NOTEBOOK_PREFIX + col_name).lower()
        nb = nb_by_title.get(paired_title)
        if nb:
            nb_display = nb["title"]
            nb_id = nb["id"][:8] + "..."
        else:
            nb_display = "(no notebook yet)"
            nb_id = ""
        print(f"{col_name:<{COL_W}}  {nb_display:<{NB_W}}  {nb_id}")

    # Also list notebooks that have no matching Zotero collection
    paired_titles = {(NOTEBOOK_PREFIX + c["data"]["name"]).lower() for c in collections}
    orphans = [nb for nb in notebooks if nb["title"].lower() not in paired_titles
               and nb["title"].lower().startswith(NOTEBOOK_PREFIX.lower())]
    if orphans:
        print("\nNotebookLM notebooks with no matching Zotero collection:")
        for nb in orphans:
            print(f"  {nb['title']}  ({nb['id'][:8]}...)")

    print(f"\nUsage: zotero-notebooklm \"Collection Name\"")
    print(f"       zotero-notebooklm \"Collection Name\" --sync   # add new papers only")


def cmd_config():
    """Interactively create the global config file."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env_path = GLOBAL_CONFIG_DIR / ".env"

    print(f"Global config: {env_path}")
    print("Get your credentials at https://www.zotero.org/settings/keys\n")

    library_id = input("Zotero Library ID (numeric user ID): ").strip()
    api_key = input("Zotero API Key: ").strip()
    library_type = input("Library type [user/group] (default: user): ").strip() or "user"

    default_storage = get_default_zotero_storage_dir()
    print(f"\nZotero data directory (the folder shown in Zotero → Edit → Preferences → Advanced)")
    print(f"  Auto-detected: {default_storage.parent}")
    data_dir_input = input("  Press Enter to accept, or type a custom path: ").strip()

    if data_dir_input:
        storage_dir = str(Path(data_dir_input) / "storage")
    else:
        storage_dir = str(default_storage)

    lines = (
        f"ZOTERO_LIBRARY_ID={library_id}\n"
        f"ZOTERO_API_KEY={api_key}\n"
        f"ZOTERO_LIBRARY_TYPE={library_type}\n"
        f"ZOTERO_DATA_DIR={storage_dir}\n"
    )
    env_path.write_text(lines)
    os.chmod(env_path, 0o600)
    print(f"\nCredentials saved to {env_path} (permissions: 600)")
    print(f"Zotero storage dir: {storage_dir}")


def cmd_skill_install():
    """Install the Claude Code skill."""
    if not SKILL_SRC.exists():
        print(f"Error: skill.md not found at {SKILL_SRC}")
        sys.exit(1)
    SKILL_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SRC, SKILL_DEST)
    print(f"Skill installed to {SKILL_DEST}")
    print("Claude Code will now recognize /zotero-notebooklm commands.")


def cmd_export(args, zot, storage_dir):
    """Export a Zotero collection to NotebookLM, with optional sync."""
    collection = find_collection(zot, args.collection)
    col_name = collection["data"]["name"]
    col_key = collection["key"]
    print(f"Collection: '{col_name}' ({col_key})")

    print("Fetching PDF attachments...")
    pdfs = get_pdf_attachments(zot, col_key)
    if not pdfs:
        print("No PDF attachments found in this collection.")
        sys.exit(0)
    print(f"Found {len(pdfs)} PDF(s) in Zotero.")

    # Resolve target notebook
    notebook_id = args.notebook
    existing_titles = set()

    if args.sync or args.notebook:
        # Try to find paired notebook if no explicit ID given
        if not notebook_id:
            notebooks = get_all_notebooks()
            paired = find_paired_notebook(col_name, notebooks)
            if paired:
                notebook_id = paired["id"]
                print(f"Found paired notebook: '{paired['title']}' ({notebook_id[:8]}...)")
            else:
                print(f"No paired notebook found for '{col_name}' — creating a new one.")

        if notebook_id:
            notebooklm("use", notebook_id)
            if args.sync:
                print("Fetching existing sources from NotebookLM...")
                existing_titles = get_notebook_source_titles(notebook_id)
                print(f"  {len(existing_titles)} source(s) already in notebook.")

    if not notebook_id:
        notebook_id = create_notebook(col_name)
    elif not args.notebook and not args.sync:
        # notebook_id came from --notebook flag
        notebooklm("use", notebook_id)
        print(f"Using notebook: {notebook_id}")

    # Filter out already-present papers in sync mode
    if args.sync and existing_titles:
        before = len(pdfs)
        pdfs = [(k, t, lm, lp) for k, t, lm, lp in pdfs
                if _normalise_title(sanitize_filename(t)) not in existing_titles]
        skipped = before - len(pdfs)
        if skipped:
            print(f"Skipping {skipped} already-present paper(s).")
        if not pdfs:
            print("Nothing new to add — notebook is up to date.")
            return

    print(f"Uploading {len(pdfs)} PDF(s)...")
    with tempfile.TemporaryDirectory() as tmpdir:
        success, failed = 0, 0
        for item_key, title, link_mode, local_path in pdfs:
            print(f"  [{success + failed + 1}/{len(pdfs)}] {title[:72]}")
            pdf_path = download_pdf(zot, item_key, title, link_mode, local_path, tmpdir, storage_dir)
            if not pdf_path:
                failed += 1
                continue
            rc, _, err = notebooklm("source", "add", pdf_path)
            if rc == 0:
                success += 1
            else:
                print(f"    Warning: failed to add to NotebookLM: {err}")
                failed += 1

    print(f"\nDone. {success} source(s) added, {failed} failed.")
    if success > 0:
        print("Sources are processing in NotebookLM (may take 30s–2min each).")
        print("Check status: notebooklm source list")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="zotero-notebooklm",
        description="Export Zotero collections to Google NotebookLM",
    )
    subparsers = parser.add_subparsers(dest="command")

    # skill subcommand
    skill_parser = subparsers.add_parser("skill", help="Manage Claude Code skill")
    skill_sub = skill_parser.add_subparsers(dest="skill_command")
    skill_sub.add_parser("install", help="Install Claude Code skill")

    # config subcommand
    subparsers.add_parser("config", help="Set up global credentials interactively")

    # export / list (default, positional)
    parser.add_argument("collection", nargs="?", help="Zotero collection name (partial match ok)")
    parser.add_argument("--notebook", help="Target a specific NotebookLM notebook ID")
    parser.add_argument("--sync", action="store_true",
                        help="Add only new papers to the existing paired notebook")
    parser.add_argument("--zotero-dir", help="Path to Zotero storage folder (overrides auto-detection)")

    args = parser.parse_args()

    # Load credentials here (not at module level) so the Windows .exe launcher
    # doesn't interfere with cwd-based .env discovery.
    # Local .env takes priority; global config is fallback.
    # find_dotenv(usecwd=True) searches upward from os.getcwd(), not the module file
    load_dotenv(find_dotenv(usecwd=True), encoding="utf-8")
    load_dotenv(Path.home() / ".zotero_notebooklm" / ".env", encoding="utf-8")

    # Route named subcommands
    if args.command == "skill":
        if args.skill_command == "install":
            cmd_skill_install()
        else:
            skill_parser.print_help()
        return

    if args.command == "config":
        cmd_config()
        return

    # Default: list or export
    zot = get_zotero_client()

    storage_dir_env = os.environ.get("ZOTERO_DATA_DIR")
    storage_dir = args.zotero_dir or storage_dir_env or str(get_default_zotero_storage_dir())
    # If the path points to the Zotero data root (not the storage subfolder), auto-append 'storage'
    storage_path = Path(storage_dir)
    if storage_path.exists() and not storage_path.name == "storage":
        candidate = storage_path / "storage"
        if candidate.exists():
            storage_dir = str(candidate)
            storage_path = candidate
    if not storage_path.exists():
        print(f"Note: local Zotero storage not found at '{storage_dir}' — local fallback disabled.")
        storage_dir = None

    if not args.collection:
        cmd_list(zot)
        return

    cmd_export(args, zot, storage_dir)


if __name__ == "__main__":
    main()
