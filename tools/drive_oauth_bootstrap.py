#!/usr/bin/env python3
"""One-time Google Drive OAuth bootstrap — run on YOUR OWN computer, not in the cloud container.

Uses Google's supported installed-app flow with a loopback redirect (http://127.0.0.1:<random port>),
NOT the deprecated out-of-band (OOB) copy/paste flow, and not the device flow (which only allows
drive.file / drive.appdata).

  pip install google-auth-oauthlib
  python drive_oauth_bootstrap.py client_secret_XXXX.json

1. Your browser opens Google's consent page. Sign in as the Drive account that owns the studio
   output folder (yukikimchi2@gmail.com) and approve.
2. The script prints three values. Put them into the cloud environment's secrets
   (environment menu → Edit → environment variables / network secrets) as:
     STUDIO_DRIVE_OAUTH_CLIENT_ID, STUDIO_DRIVE_OAUTH_CLIENT_SECRET, STUDIO_DRIVE_OAUTH_REFRESH_TOKEN
   Never commit them, never paste them into chat. Start a new session afterwards.
3. Delete client_secret_XXXX.json from your Downloads when done (optional --write-env FILE writes the
   values to a file with 0600 permissions instead of printing them).

Security: PKCE (S256) is always used; the `state` value is generated per run and a mismatching
redirect is rejected (oauthlib MismatchingStateError) before any token request.

Scope (--scope):
  drive       (default) needed to write into the EXISTING output folder "Cloud Video Production
              Studio", which was created by another app (the Claude Google Drive connector).
              Restricted scope: unverified-app warning; personal use only.
  drive.file  least privilege (non-sensitive) but this client can only reach files/folders it
              created itself or that were granted to it through the Google Picker — it would NOT
              see the existing output folder. Use only together with a new output tree created by
              this client (studio drive setup --parent root), and set
              STUDIO_DRIVE_OAUTH_SCOPE=https://www.googleapis.com/auth/drive.file in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

SCOPE_CHOICES = {"drive": "https://www.googleapis.com/auth/drive",
                 "drive.file": "https://www.googleapis.com/auth/drive.file"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client_secret_json", help="OAuth client (type: Desktop app) JSON downloaded from Google Cloud Console")
    ap.add_argument("--write-env", help="write KEY=VALUE lines to this file (chmod 600) instead of printing")
    ap.add_argument("--scope", choices=sorted(SCOPE_CHOICES), default="drive")
    args = ap.parse_args()
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Install first: pip install google-auth-oauthlib", file=sys.stderr)
        return 2
    with open(args.client_secret_json, encoding="utf-8") as f:
        kind = next(iter(json.load(f)), "")
    if kind != "installed":
        print(f"This JSON is a '{kind}' client. Create an OAuth client of type 'Desktop app' instead.", file=sys.stderr)
        return 2
    scope = SCOPE_CHOICES[args.scope]
    flow = InstalledAppFlow.from_client_secrets_file(args.client_secret_json, [scope],
                                                     autogenerate_code_verifier=True)   # PKCE S256
    # host 127.0.0.1 + port 0 = loopback redirect on a free port; offline + consent => refresh token
    creds = flow.run_local_server(host="127.0.0.1", port=0, access_type="offline", prompt="consent",
                                  open_browser=True)
    if not creds.refresh_token:
        print("Google returned no refresh token. Revoke the app at https://myaccount.google.com/permissions "
              "and run again.", file=sys.stderr)
        return 1
    lines = [f"STUDIO_DRIVE_OAUTH_CLIENT_ID={creds.client_id}",
             f"STUDIO_DRIVE_OAUTH_CLIENT_SECRET={creds.client_secret}",
             f"STUDIO_DRIVE_OAUTH_REFRESH_TOKEN={creds.refresh_token}"]
    if scope != SCOPE_CHOICES["drive"]:
        lines.append(f"STUDIO_DRIVE_OAUTH_SCOPE={scope}")
    if args.write_env:
        fd = os.open(args.write_env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Wrote 3 values to {args.write_env} (permissions 600). Copy them into the environment secrets.")
    else:
        print("\nAdd these three values to the cloud environment secrets (do not commit / do not paste in chat):\n")
        print("\n".join(lines))
    print("\nGranted scopes:", " ".join(creds.scopes or [scope]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
