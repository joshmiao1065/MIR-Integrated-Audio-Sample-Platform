#!/usr/bin/env python3
"""
One-time script to authorise Google Drive access for your personal Google account.

Run this ONCE after creating OAuth2 credentials in Google Cloud Console.  It
opens an authorisation URL in your browser (or prints it for manual use on
WSL2), completes the OAuth2 flow, and prints the refresh token.  Copy that
token into your .env as GDRIVE_REFRESH_TOKEN.

The refresh token does not expire unless you revoke access or leave it unused
for more than 6 months.  You do NOT need to re-run this script each deployment —
just copy the token into Railway's environment variables alongside
GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET.

Usage
-----
From the repo root:

    python -m scripts.gdrive_auth --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET

On WSL2
-------
The script starts a local HTTP server on port 8080 to receive Google's
redirect after you approve access.  WSL2 forwards localhost to Windows, so:

  1. The script prints an authorisation URL.
  2. Paste it into your Windows browser.
  3. Log in with the Google account that has your Google One plan.
  4. Approve "See, edit, create, and delete all your Google Drive files".
  5. The browser redirects to http://localhost:8080/?code=...
     WSL2's localhost proxy forwards this to the script's server.
  6. The script prints your GDRIVE_REFRESH_TOKEN.

If the browser redirect fails (e.g. "Connection refused"), run with
--no-server to switch to the manual copy-paste mode instead.

Manual / copy-paste mode (--no-server)
---------------------------------------
    python -m scripts.gdrive_auth --client-id ID --client-secret SECRET --no-server

  1. The script prints an authorisation URL.
  2. Open it in any browser and approve access.
  3. Google shows a page with an authorisation code — copy it.
  4. Paste the code back into the terminal when prompted.
  5. The script prints your GDRIVE_REFRESH_TOKEN.
"""

import argparse
import sys
from pathlib import Path

# Allow running directly from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/drive"]

_CLIENT_CONFIG_TEMPLATE = {
    "installed": {
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


def _build_client_config(client_id: str, client_secret: str) -> dict:
    cfg = dict(_CLIENT_CONFIG_TEMPLATE)
    cfg["installed"] = dict(cfg["installed"])
    cfg["installed"]["client_id"] = client_id
    cfg["installed"]["client_secret"] = client_secret
    return cfg


def run_server_flow(client_id: str, client_secret: str, port: int) -> str:
    """Start a local HTTP server on *port* and complete the OAuth2 flow.

    The auth URL is printed so you can paste it into a browser manually
    (required on WSL2 where the script cannot open a browser automatically).
    """
    flow = InstalledAppFlow.from_client_config(
        _build_client_config(client_id, client_secret),
        scopes=_SCOPES,
    )

    print()
    print("=" * 72)
    print("STEP 1 — Open the URL below in your browser (Windows browser on WSL2):")
    print("=" * 72)

    creds = flow.run_local_server(
        port=port,
        open_browser=False,  # don't try to open a browser from WSL2/server
        # Suppress the default "Please visit this URL" message so we control
        # the UX ourselves via the prompt above.
        prompt="consent",
        access_type="offline",
    )
    return creds.refresh_token


def run_manual_flow(client_id: str, client_secret: str) -> str:
    """Purely console-based flow — no local HTTP server needed.

    Prints the auth URL, prompts for the authorisation code, and exchanges it
    for tokens.  Use this if the local-server redirect fails on WSL2.
    """
    import urllib.parse
    import urllib.request
    import json

    auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        + urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "response_type": "code",
                "scope": " ".join(_SCOPES),
                "access_type": "offline",
                "prompt": "consent",
            }
        )
    )

    print()
    print("=" * 72)
    print("STEP 1 — Open this URL in your browser:")
    print("=" * 72)
    print(auth_url)
    print()
    print("Log in with the Google account that owns your Google One plan.")
    print("Approve 'See, edit, create, and delete all your Google Drive files'.")
    print("Google will show a page with an authorisation code — copy it.")
    print()

    auth_code = input("STEP 2 — Paste the authorisation code here and press Enter: ").strip()
    if not auth_code:
        print("ERROR: No authorisation code provided.", file=sys.stderr)
        sys.exit(1)

    # Exchange the code for tokens via a direct POST.
    data = urllib.parse.urlencode(
        {
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "authorization_code",
        }
    ).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"ERROR: Token exchange failed ({exc.code}): {body}", file=sys.stderr)
        sys.exit(1)

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print(
            "ERROR: No refresh_token in response.  Make sure you approved with "
            "access_type=offline and the consent screen was shown.",
            file=sys.stderr,
        )
        sys.exit(1)

    return refresh_token


def print_result(refresh_token: str) -> None:
    print()
    print("=" * 72)
    print("SUCCESS — copy the lines below into your .env file:")
    print("=" * 72)
    print(f"GDRIVE_REFRESH_TOKEN={refresh_token}")
    print()
    print("Also add to Railway environment variables if deploying there.")
    print()
    print("You do NOT need to re-run this script.  The refresh token is")
    print("permanent unless you revoke access in your Google Account settings.")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "One-time OAuth2 authorisation for Google Drive. "
            "Run once to get a refresh token, then store it in .env."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--client-id",
        required=True,
        metavar="CLIENT_ID",
        help="OAuth2 Client ID from Google Cloud Console (Desktop app credential)",
    )
    parser.add_argument(
        "--client-secret",
        required=True,
        metavar="CLIENT_SECRET",
        help="OAuth2 Client Secret from Google Cloud Console",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local port for the OAuth2 redirect server (default: 8080)",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help=(
            "Use manual copy-paste flow instead of a local redirect server. "
            "Useful if localhost:PORT is unreachable from your browser."
        ),
    )
    args = parser.parse_args()

    try:
        if args.no_server:
            refresh_token = run_manual_flow(args.client_id, args.client_secret)
        else:
            refresh_token = run_server_flow(args.client_id, args.client_secret, args.port)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)

    print_result(refresh_token)


if __name__ == "__main__":
    main()
