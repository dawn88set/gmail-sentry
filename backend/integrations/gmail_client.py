"""
Gmail provider client (REST via httpx) — the reference byo-oauth client.

Reads/refreshes the user's stored OAuth tokens (never reads provider keys from
env). After use, persist `client.credentials` so any refreshed access token is
saved. Generated app code should import and call this rather than hand-rolling
Gmail/OAuth.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1"


class GmailNotConnected(Exception):
    """Raised when there is no usable Gmail credential for the user."""


class GmailClient:
    """
    Construct with the user's decrypted credentials dict:
        { client_id, client_secret, access_token, refresh_token, token_expiry? }
    The instance keeps a working copy of the credentials and refreshes the access
    token on demand; read `.credentials` afterwards to persist refreshed tokens.
    """

    def __init__(self, creds: Dict[str, Any]):
        if not creds or not creds.get("access_token"):
            raise GmailNotConnected("Gmail is not connected.")
        self.credentials: Dict[str, Any] = dict(creds)

    def _refresh(self) -> None:
        refresh_token = self.credentials.get("refresh_token")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        if not (refresh_token and client_id and client_secret):
            raise GmailNotConnected("Cannot refresh Gmail token; reconnect Gmail.")
        resp = httpx.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        tok = resp.json()
        self.credentials["access_token"] = tok["access_token"]
        if tok.get("expires_in"):
            self.credentials["token_expiry"] = (
                datetime.utcnow() + timedelta(seconds=int(tok["expires_in"]))
            ).isoformat()

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        def _do():
            return httpx.request(
                method,
                f"{API_BASE}{path}",
                headers={"Authorization": f"Bearer {self.credentials['access_token']}"},
                timeout=30,
                **kwargs,
            )

        resp = _do()
        if resp.status_code == 401:
            self._refresh()
            resp = _do()
        resp.raise_for_status()
        return resp.json()

    def list_messages(self, query: str = "", max_results: int = 25) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        return self._request("GET", "/users/me/messages", params=params).get("messages", [])

    def get_message(self, message_id: str, fmt: str = "metadata") -> Dict[str, Any]:
        return self._request("GET", f"/users/me/messages/{message_id}", params={"format": fmt})

    def modify_labels(
        self,
        message_id: str,
        add: Optional[List[str]] = None,
        remove: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/users/me/messages/{message_id}/modify",
            json={"addLabelIds": add or [], "removeLabelIds": remove or []},
        )

    def trash(self, message_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/users/me/messages/{message_id}/trash")

    def send(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a plain-text email; returns Gmail's response (incl. the message id).

        Builds a minimal RFC 2822 message, base64url-encodes it, and POSTs to
        users/me/messages/send. Pass thread_id/in_reply_to to keep a reply in
        the original conversation.
        """
        import base64
        from email.mime.text import MIMEText

        mime = MIMEText(body or "", _charset="utf-8")
        mime["To"] = to
        mime["Subject"] = subject or ""
        if in_reply_to:
            mime["In-Reply-To"] = in_reply_to
            mime["References"] = in_reply_to
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
        payload: Dict[str, Any] = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        return self._request("POST", "/users/me/messages/send", json=payload)

    def profile_email(self) -> Optional[str]:
        return self._request("GET", "/users/me/profile").get("emailAddress")
