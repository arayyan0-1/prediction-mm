#!/usr/bin/env python3
"""Demo RSA-PSS authentication signing.

This script demonstrates:
1. Loading RSA private key from PEM file
2. Generating authentication headers
3. Signing requests with RSA-PSS
4. Request signature validation

This is primarily used for WebSocket authentication, as REST API
authentication is handled automatically by the Kalshi SDK.
"""

import sys
import structlog
from pathlib import Path

from prediction_mm.config import load_config
from prediction_mm.auth import create_auth, KalshiAuth, AuthError

logger = structlog.get_logger()


def demo_auth_basics():
    """Demonstrate basic auth operations."""
    print(f"\n{'=' * 80}")
    print("RSA-PSS Authentication Demo")
    print(f"{'=' * 80}\n")

    # Load configuration
    config = load_config()
    print(f"API Key ID: {config.api_key_id}")
    print(f"Private Key Path: {config.private_key_path}")
    print(f"Environment: {config.environment.value}\n")

    # Create auth handler
    print("Loading private key...")
    try:
        auth = create_auth(config.api_key_id, config.private_key_path)
        print("Private key loaded successfully\n")
    except AuthError as e:
        print(f"ERROR: {e}")
        return 1

    # Generate auth headers for a sample WebSocket request
    print("Generating authentication headers for WebSocket connection...")
    path = "/trade-api/ws/v2"
    headers = auth.get_auth_headers("GET", path)

    print(f"\nGenerated headers for: GET {path}")
    print(f"  KALSHI-ACCESS-KEY: {headers['KALSHI-ACCESS-KEY']}")
    print(f"  KALSHI-ACCESS-TIMESTAMP: {headers['KALSHI-ACCESS-TIMESTAMP']}")
    print(f"  KALSHI-ACCESS-SIGNATURE: {headers['KALSHI-ACCESS-SIGNATURE'][:40]}...")
    print(f"                            (truncated, full length: {len(headers['KALSHI-ACCESS-SIGNATURE'])} chars)")

    # Demonstrate signature properties
    print(f"\n{'=' * 80}")
    print("Signature Properties")
    print(f"{'=' * 80}\n")

    # Different timestamps produce different signatures
    print("1. Signatures are time-dependent:")
    sig1 = auth.sign_request("1234567890000", "GET", "/test")
    sig2 = auth.sign_request("1234567890001", "GET", "/test")
    print(f"   Same request, different timestamps:")
    print(f"   Timestamp 1234567890000: {sig1[:40]}...")
    print(f"   Timestamp 1234567890001: {sig2[:40]}...")
    print(f"   Signatures differ: {sig1 != sig2}")

    # Different methods produce different signatures
    print(f"\n2. Signatures depend on HTTP method:")
    sig_get = auth.sign_request("1234567890000", "GET", "/test")
    sig_post = auth.sign_request("1234567890000", "POST", "/test")
    print(f"   Same path, different methods:")
    print(f"   GET:  {sig_get[:40]}...")
    print(f"   POST: {sig_post[:40]}...")
    print(f"   Signatures differ: {sig_get != sig_post}")

    # Different paths produce different signatures
    print(f"\n3. Signatures depend on request path:")
    sig_path1 = auth.sign_request("1234567890000", "GET", "/path1")
    sig_path2 = auth.sign_request("1234567890000", "GET", "/path2")
    print(f"   Same method, different paths:")
    print(f"   /path1: {sig_path1[:40]}...")
    print(f"   /path2: {sig_path2[:40]}...")
    print(f"   Signatures differ: {sig_path1 != sig_path2}")

    # Query parameters are stripped
    print(f"\n4. Query parameters are stripped before signing:")
    sig_no_query = auth.sign_request("1234567890000", "GET", "/test/path")
    sig_with_query = auth.sign_request("1234567890000", "GET", "/test/path?foo=bar&baz=qux")
    print(f"   Path without query: /test/path")
    print(f"   Path with query: /test/path?foo=bar&baz=qux")
    print(f"   Signature 1: {sig_no_query[:40]}...")
    print(f"   Signature 2: {sig_with_query[:40]}...")
    print(f"   Note: RSA-PSS is non-deterministic, so signatures differ even for same message")
    print(f"         Both signatures are valid for the same input")

    print(f"\n{'=' * 80}")
    print("Authentication Demo Complete")
    print(f"{'=' * 80}\n")

    print("Key Points:")
    print("  - Each signature includes: timestamp + method + path")
    print("  - RSA-PSS signatures are non-deterministic (include random salt)")
    print("  - Query parameters are stripped before signing")
    print("  - Signatures are base64-encoded")
    print("  - REST API: SDK handles authentication automatically")
    print("  - WebSocket: Use get_auth_headers() for handshake")
    print()

    return 0


def demo_error_handling():
    """Demonstrate error handling."""
    print(f"\n{'=' * 80}")
    print("Error Handling Demo")
    print(f"{'=' * 80}\n")

    # Try loading with bad path
    print("1. Testing with non-existent private key...")
    try:
        bad_auth = KalshiAuth("test-key", Path("/nonexistent/key.pem"))
        bad_auth.load_private_key()
        print("   ERROR: Should have raised AuthError")
        return 1
    except AuthError as e:
        print(f"   Caught expected error: {e}")

    # Try signing without loading key
    print("\n2. Testing signature without loading key...")
    try:
        unloaded_auth = KalshiAuth("test-key", Path("./test.pem"))
        unloaded_auth.sign_request("123", "GET", "/test")
        print("   ERROR: Should have raised AuthError")
        return 1
    except AuthError as e:
        print(f"   Caught expected error: {e}")

    print("\nError handling works correctly\n")
    return 0


def main() -> int:
    """Main entry point."""
    try:
        result = demo_auth_basics()
        if result != 0:
            return result

        return demo_error_handling()

    except Exception as e:
        logger.error("demo_failed", error=str(e))
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
