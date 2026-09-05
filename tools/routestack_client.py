import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time

import requests

from config.config import (
    ROUTESTACK_ACCOUNT_ID,
    ROUTESTACK_API_KEY,
    ROUTESTACK_API_SECRET,
    ROUTESTACK_ENDPOINT,
)

TOKEN_CACHE_FILE = Path(__file__).resolve().parent.parent / ".routestack_token_cache.json"


class RouteStackError(RuntimeError):
    """Base error for RouteStack failures."""


class RouteStackAuthError(RouteStackError):
    """Raised when RouteStack authentication fails."""


class RouteStackClient:
    def __init__(self):
        self.base_url = ROUTESTACK_ENDPOINT.rstrip("/")
        self.account_id = ROUTESTACK_ACCOUNT_ID
        self.api_key = ROUTESTACK_API_KEY
        self.api_secret = ROUTESTACK_API_SECRET
        self.token = None

        self._validate_config()

    def _validate_config(self):
        missing = []
        if not self.api_key:
            missing.append("ROUTESTACK_API_KEY")
        if not self.api_secret:
            missing.append("ROUTESTACK_API_SECRET")
        if not self.base_url:
            missing.append("ROUTESTACK_ENDPOINT")

        if missing:
            raise RouteStackAuthError(
                "Missing RouteStack configuration: " + ", ".join(missing)
            )

    def _get_cached_token(self):
        if not TOKEN_CACHE_FILE.exists():
            return None
        try:
            data = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
            token = data.get("token")
            expires_at = data.get("expires_at", 0)
            if token and expires_at > time.time() + 300:
                return token
        except Exception:
            pass
        return None

    def _save_cached_token(self, token, expires_in_seconds=82800):
        try:
            data = {
                "token": token,
                "expires_at": time.time() + expires_in_seconds
            }
            TOKEN_CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def authenticate(self):
        cached = self._get_cached_token()
        if cached:
            self.token = cached
            return cached

        timestamp = int(time.time())
        nonce = secrets.token_hex(16)

        message = f"{self.api_key}:{timestamp}:{nonce}"
        raw_sig = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64encode(raw_sig).decode("utf-8").rstrip("=")

        payload = {
            "apiKey": self.api_key,
            "timestamp": timestamp,
            "nonce": nonce,
            "hmac": signature
        }

        url = f"{self.base_url}/mcp/auth/partner-token"

        try:
            response = requests.post(url, json=payload, timeout=30)
        except requests.RequestException as exc:
            if cached:
                self.token = cached
                return cached
            raise RouteStackError(
                f"Could not reach RouteStack authentication endpoint: {exc}"
            ) from exc

        if response.status_code == 429:
            # Rate limited on partner-token; reuse cached token if available
            if TOKEN_CACHE_FILE.exists():
                try:
                    data = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
                    fallback = data.get("token")
                    if fallback:
                        self.token = fallback
                        return fallback
                except Exception:
                    pass
            raise RouteStackError("RouteStack authentication rate limited (HTTP 429). Please retry shortly.")

        if response.status_code == 401:
            detail = ""
            try:
                body = response.json()
                detail = body.get("message") or body.get("detail") or ""
            except ValueError:
                pass

            raise RouteStackAuthError(
                "RouteStack authentication returned HTTP 401. "
                "Check that ROUTESTACK_API_KEY and ROUTESTACK_API_SECRET "
                "belong to the same RouteStack environment/account and that "
                f"ROUTESTACK_ENDPOINT is correct. {detail}".strip()
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RouteStackError(
                f"RouteStack authentication failed with HTTP "
                f"{response.status_code}: {response.text[:300]}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise RouteStackError(
                "RouteStack authentication returned non-JSON data."
            ) from exc

        token = data.get("token") or data.get("accessToken")
        if not token:
            raise RouteStackAuthError(
                "RouteStack authentication succeeded but no token was returned."
            )

        self.token = token
        self._save_cached_token(token)
        return token

    def _headers(self):
        if not self.token:
            self.authenticate()

        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def post(self, endpoint, payload):
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=60
            )
        except requests.RequestException as exc:
            raise RouteStackError(
                f"RouteStack request failed: {exc}"
            ) from exc

        # Retry once only when the bearer token itself expired.
        if response.status_code == 401:
            self.token = None
            self.authenticate()

            try:
                response = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=60
                )
            except requests.RequestException as exc:
                raise RouteStackError(
                    f"RouteStack retry failed: {exc}"
                ) from exc

            if response.status_code == 401:
                raise RouteStackAuthError(
                    "RouteStack rejected the authenticated request with HTTP 401."
                )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RouteStackError(
                f"RouteStack request failed with HTTP "
                f"{response.status_code}: {response.text[:500]}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RouteStackError(
                "RouteStack returned a non-JSON response."
            ) from exc

    # HOTEL API
    def search_hotel_destination(self, query):
        return self.post(
            "/mcp/hotel/search-destinations",
            {"type": "DESTINATION", "query": query}
        )

    def search_hotels(
        self,
        destination_id,
        latitude,
        longitude,
        check_in,
        check_out,
        rooms
    ):
        payload = {
            "destinationId": destination_id,
            "lat": latitude,
            "long": longitude,
            "checkIn": check_in,
            "checkOut": check_out,
            "rooms": rooms,
            "roomCount": len(rooms),
            "limit": 20,
            "page": 1
        }
        return self.post("/mcp/hotel/search-hotels", payload)

    def get_hotel_details_and_rates(
        self,
        hotel_id,
        token,
        correlation_id,
        check_in,
        check_out,
        rooms,
        hotel_name=None
    ):
        payload = {
            "hotelId": str(hotel_id),
            "token": token,
            "correlationId": correlation_id,
            "checkIn": check_in,
            "checkOut": check_out,
            "rooms": rooms,
            "contentType": "ALL"
        }
        if hotel_name:
            payload["hotelName"] = hotel_name

        return self.post(
            "/mcp/hotel/get-hotel-details-and-rates",
            payload
        )
