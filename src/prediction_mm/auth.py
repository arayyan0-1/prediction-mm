"""RSA-PSS authentication for Kalshi API.

This module provides RSA-PSS request signing required for Kalshi WebSocket authentication.
REST API authentication is handled automatically by the Kalshi SDK.
"""

import base64
import time
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class AuthError(Exception):
    """Raised when authentication fails."""


class KalshiAuth:
    """RSA-PSS request signer for Kalshi WebSocket authentication.

    Kalshi WebSocket connections require authentication headers:
    - KALSHI-ACCESS-KEY: Your API key ID
    - KALSHI-ACCESS-TIMESTAMP: Current timestamp in milliseconds
    - KALSHI-ACCESS-SIGNATURE: RSA-PSS signature of (timestamp + method + path)

    Note: REST API authentication is handled automatically by the Kalshi SDK.
          This class is primarily used for WebSocket authentication.

    Usage:
        ```python
        auth = create_auth(api_key_id, private_key_path)
        headers = auth.get_auth_headers("GET", "/trade-api/ws/v2")
        # Use headers in WebSocket connection
        ```

    Attributes:
        api_key_id: The API key ID for authentication.
    """

    def __init__(self, api_key_id: str, private_key_path: Path):
        """Initialize authentication handler.

        Args:
            api_key_id: Your Kalshi API key ID.
            private_key_path: Path to your RSA private key PEM file.
        """
        self._api_key_id = api_key_id
        self._private_key_path = private_key_path
        self._private_key: rsa.RSAPrivateKey | None = None

    @property
    def api_key_id(self) -> str:
        """Get the API key ID.

        Returns:
            The API key ID string.
        """
        return self._api_key_id

    def load_private_key(self) -> None:
        """Load the RSA private key from file.

        Raises:
            AuthError: If key file cannot be found or parsed.
        """
        try:
            with open(self._private_key_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend(),
                )
        except FileNotFoundError:
            raise AuthError(f"Private key file not found: {self._private_key_path}")
        except Exception as e:
            raise AuthError(f"Failed to load private key: {e}") from e

    def sign_request(self, timestamp_ms: str, method: str, path: str) -> str:
        """Sign a request using RSA-PSS.

        The signature is generated over the concatenation of:
        timestamp_ms + method.upper() + path (without query parameters)

        Args:
            timestamp_ms: Timestamp in milliseconds as string.
            method: HTTP method (GET, POST, DELETE, etc.).
            path: API path. Query parameters will be stripped before signing.

        Returns:
            Base64-encoded RSA-PSS signature.

        Raises:
            AuthError: If private key has not been loaded.
        """
        if self._private_key is None:
            raise AuthError("Private key not loaded. Call load_private_key() first.")

        # Strip query parameters from path
        path_without_query = path.split("?")[0]

        # Construct message: timestamp + method + path
        message = f"{timestamp_ms}{method.upper()}{path_without_query}"
        message_bytes = message.encode("utf-8")

        # Sign with RSA-PSS using SHA256
        signature = self._private_key.sign(
            message_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

        return base64.b64encode(signature).decode("utf-8")

    def get_auth_headers(self, method: str, path: str) -> dict[str, str]:
        """Generate authentication headers for an API request.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path. Query parameters will be stripped for signing.

        Returns:
            Dictionary with KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP,
            and KALSHI-ACCESS-SIGNATURE headers.

        Raises:
            AuthError: If private key has not been loaded.
        """
        timestamp_ms = str(int(time.time() * 1000))
        signature = self.sign_request(timestamp_ms, method, path)

        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }


def create_auth(api_key_id: str, private_key_path: Path) -> KalshiAuth:
    """Create and initialize a KalshiAuth instance.

    This is a convenience function that creates a KalshiAuth instance
    and automatically loads the private key.

    Args:
        api_key_id: Your Kalshi API key ID.
        private_key_path: Path to your RSA private key PEM file.

    Returns:
        Initialized KalshiAuth instance with private key loaded.

    Raises:
        AuthError: If private key cannot be loaded.
    """
    auth = KalshiAuth(api_key_id, private_key_path)
    auth.load_private_key()
    return auth
