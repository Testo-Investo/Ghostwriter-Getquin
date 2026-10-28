"""Microsoft-Graph-Client mit Device-Code-Login und persistentem Token-Cache."""

import os
from pathlib import Path

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read", "Chat.ReadWrite", "Files.Read.All", "Sites.Read.All"]
CACHE_FILE = Path(".token_cache.json")

# Ohne eigene App-Registrierung: Microsofts offizieller öffentlicher Client
# "Microsoft Graph Command Line Tools" (wird u. a. von Graph PowerShell genutzt).
DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"


class GraphClient:
    def __init__(self, tenant_id: str | None = None, client_id: str | None = None):
        tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID") or "organizations"
        client_id = client_id or os.getenv("AZURE_CLIENT_ID") or DEFAULT_CLIENT_ID
        self._cache = msal.SerializableTokenCache()
        if CACHE_FILE.exists():
            self._cache.deserialize(CACHE_FILE.read_text())
        self._app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )
        self._session = requests.Session()

    def _token(self) -> str:
        accounts = self._app.get_accounts()
        result = self._app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
        if not result:
            flow = self._app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Device-Flow fehlgeschlagen: {flow}")
            print(flow["message"], flush=True)
            result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Login fehlgeschlagen: {result.get('error_description')}")
        if self._cache.has_state_changed:
            CACHE_FILE.write_text(self._cache.serialize())
            CACHE_FILE.chmod(0o600)
        return result["access_token"]

    def request(self, method: str, path_or_url: str, **kwargs) -> requests.Response:
        url = path_or_url if path_or_url.startswith("http") else f"{GRAPH}{path_or_url}"
        headers = {"Authorization": f"Bearer {self._token()}", **kwargs.pop("headers", {})}
        resp = self._session.request(method, url, headers=headers, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp

    def get(self, path: str, **kwargs) -> dict:
        return self.request("GET", path, **kwargs).json()

    def paged(self, path: str, **kwargs):
        """Iteriert über alle Seiten einer Graph-Collection (@odata.nextLink)."""
        data = self.get(path, **kwargs)
        while True:
            yield from data.get("value", [])
            next_link = data.get("@odata.nextLink")
            if not next_link:
                return
            data = self.get(next_link)
