"""auth.py
Helper utilities for loading Google Service Account credentials
and returning an authorized gspread client.
"""
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials


def load_credentials_from_file(path, scopes):
    """Load ServiceAccountCredentials from a JSON key file."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return ServiceAccountCredentials.from_json_keyfile_name(path, scopes)


def load_credentials_from_dict(dct, scopes):
    """Load ServiceAccountCredentials from a dict (e.g. streamlit secrets)."""
    if not isinstance(dct, dict):
        raise ValueError("service account dict required")
    return ServiceAccountCredentials.from_json_keyfile_dict(dct, scopes)


def get_gspread_client(secrets_path="secrets.json", st_secrets=None, scopes=None):
    """Return an authorized gspread client or None.

    Order: local `secrets.json` file -> `st_secrets['gcp_service_account']` dict -> None
    Exceptions are propagated to the caller for clearer handling.
    """
    if scopes is None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

    # 1) Try file-based credentials
    if secrets_path and os.path.exists(secrets_path):
        creds = load_credentials_from_file(secrets_path, scopes)
        return gspread.authorize(creds)

    # 2) Try streamlit-provided dict
    if st_secrets and isinstance(st_secrets, dict):
        svc = st_secrets.get("gcp_service_account") or st_secrets.get("service_account")
        if svc:
            creds = load_credentials_from_dict(svc, scopes)
            return gspread.authorize(creds)

    return None
