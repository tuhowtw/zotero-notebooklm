"""
zotero-notebooklm

Export PDFs from a Zotero collection to a Google NotebookLM notebook.

Usage:
    zotero-notebooklm                          # list all collections
    zotero-notebooklm "Collection Name"        # export collection → new notebook
    zotero-notebooklm "Collection Name" --notebook <id>  # add to existing notebook
    zotero-notebooklm --zotero-dir /path/to/storage      # override local storage path
    zotero-notebooklm skill install            # install Claude Code skill

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

from dotenv import load_dotenv
from pyzotero import zotero

# Load credentials: local .env takes priority, global config is fallback
load_dotenv()
load_dotenv(Path.home() / ".zotero_notebooklm" / ".env")

GLOBAL_CONFIG_DIR = Path.home() / ".zotero_notebooklm"
SKILL_DEST = Path.home() / ".claude" / "skills" / "zotero-notebooklm.md"
SKILL_SRC = Path(__file__).parent.parent / "skill.md"


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


def list_collections(zot):
    collections = zot.collections()
    if not collections:
        print("No collections found in your Zotero library.")
        return
    print(f"\n{'KEY':<12}  NAME")
    print("-" * 55)
    for col in sorted(collections, key=lambda c: c["data"]["name"].lower()):
        print(f"{col['key']:<12}  {col['data']['name']}")


def find_collection(zot, name):
    collections = zot.collections()
    name_lower = name.lower()
    matches = [c for c in collections if c["data"]["name"].lower() == name_lower]
    if not matches:
        matches = [c for c in collections if name_lower in c["data"]["name"].lower()]
    if not matches:
        print(f"Error: No collection matching '{name}' found.")
        print("Run without arguments to list all collections.")
        sys.exit(1)
    if len(matches) > 1:
        print(f"Ambiguous name '{name}'. Matches:")
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
# Local storage helpers
# ---------------------------------------------------------------------------

def get_default_zotero_storage_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Zotero" / "Zotero" / "storage"
    return Path.home() / "Zotero" / "storage"


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
# NotebookLM helpers
# ---------------------------------------------------------------------------

def notebooklm(*args):
    result = subprocess.run(["notebooklm", *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def create_or_use_notebook(notebook_arg, col_name):
    if notebook_arg:
        rc, _, err = notebooklm("use", notebook_arg)
        if rc != 0:
            print(f"Error: Could not use notebook '{notebook_arg}': {err}")
            sys.exit(1)
        print(f"Using existing notebook: {notebook_arg}")
        return notebook_arg

    notebook_title = f"Zotero: {col_name}"
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
# Subcommands
# ---------------------------------------------------------------------------

def cmd_config():
    """Interactively create the global config file."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env_path = GLOBAL_CONFIG_DIR / ".env"

    print(f"Global config: {env_path}")
    print("Get your credentials at https://www.zotero.org/settings/keys\n")

    library_id = input("Zotero Library ID (numeric user ID): ").strip()
    api_key = input("Zotero API Key: ").strip()
    library_type = input("Library type [user/group] (default: user): ").strip() or "user"

    env_path.write_text(
        f"ZOTERO_LIBRARY_ID={library_id}\n"
        f"ZOTERO_API_KEY={api_key}\n"
        f"ZOTERO_LIBRARY_TYPE={library_type}\n"
    )
    os.chmod(env_path, 0o600)  # owner read/write only
    print(f"\nCredentials saved to {env_path} (permissions: 600)")


def cmd_skill_install():
    """Install the Claude Code skill."""
    if not SKILL_SRC.exists():
        print(f"Error: skill.md not found at {SKILL_SRC}")
        print("Make sure you installed the package from source.")
        sys.exit(1)
    SKILL_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SRC, SKILL_DEST)
    print(f"Skill installed to {SKILL_DEST}")
    print("Claude Code will now recognize /zotero-notebooklm commands.")


def cmd_export(args, zot, storage_dir):
    """Export a Zotero collection to NotebookLM."""
    collection = find_collection(zot, args.collection)
    col_name = collection["data"]["name"]
    col_key = collection["key"]
    print(f"Collection: '{col_name}' ({col_key})")

    print("Fetching PDF attachments...")
    pdfs = get_pdf_attachments(zot, col_key)
    if not pdfs:
        print("No PDF attachments found in this collection.")
        sys.exit(0)
    print(f"Found {len(pdfs)} PDF(s).")

    create_or_use_notebook(args.notebook, col_name)

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

    # export (default, positional)
    parser.add_argument("collection", nargs="?", help="Zotero collection name (partial match ok)")
    parser.add_argument("--notebook", help="Add to existing NotebookLM notebook ID")
    parser.add_argument("--zotero-dir", help="Path to Zotero storage folder (overrides auto-detection)")

    args = parser.parse_args()

    # Route subcommands
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
    if not Path(storage_dir).exists():
        print(f"Note: local Zotero storage not found at '{storage_dir}' — local fallback disabled.")
        storage_dir = None

    if not args.collection:
        print("Available Zotero collections:")
        list_collections(zot)
        print("\nUsage: zotero-notebooklm \"Collection Name\"")
        return

    cmd_export(args, zot, storage_dir)


if __name__ == "__main__":
    main()
