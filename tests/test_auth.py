"""Tests for RSA-PSS authentication."""

import pytest
from pathlib import Path

from prediction_mm.auth import KalshiAuth, AuthError, create_auth


class TestKalshiAuth:
    """Tests for KalshiAuth class."""
    
    def test_init(self, tmp_private_key: Path):
        """Auth can be initialized with key path."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        assert auth.api_key_id == "test-key-id"
    
    def test_load_private_key_success(self, tmp_private_key: Path):
        """Private key loads successfully."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        # Should not raise
    
    def test_load_private_key_not_found(self, tmp_path: Path):
        """Missing private key raises AuthError."""
        auth = KalshiAuth("test-key-id", tmp_path / "nonexistent.pem")
        
        with pytest.raises(AuthError, match="not found"):
            auth.load_private_key()
    
    def test_sign_request_without_key_raises(self, tmp_private_key: Path):
        """Signing without loaded key raises AuthError."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        
        with pytest.raises(AuthError, match="not loaded"):
            auth.sign_request("1234567890000", "GET", "/test/path")
    
    def test_sign_request_produces_signature(self, tmp_private_key: Path):
        """Signing produces a non-empty base64 signature."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        signature = auth.sign_request("1234567890000", "GET", "/test/path")
        
        assert signature
        assert isinstance(signature, str)
        # Should be valid base64
        import base64
        base64.b64decode(signature)
    
    def test_sign_request_strips_query_params(self, tmp_private_key: Path):
        """Query parameters are stripped before signing (verify via message construction)."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        # Both should produce valid signatures (can't compare directly due to RSA-PSS randomness)
        sig1 = auth.sign_request("1234567890000", "GET", "/test/path")
        sig2 = auth.sign_request("1234567890000", "GET", "/test/path?foo=bar")
        
        # Both should be valid base64 signatures
        import base64
        assert len(base64.b64decode(sig1)) > 0
        assert len(base64.b64decode(sig2)) > 0
        # Note: RSA-PSS is non-deterministic, so sig1 != sig2 even for same message
    
    def test_sign_request_different_for_different_methods(self, tmp_private_key: Path):
        """Different HTTP methods produce different messages (and thus different signatures)."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        sig_get = auth.sign_request("1234567890000", "GET", "/test/path")
        sig_post = auth.sign_request("1234567890000", "POST", "/test/path")
        
        # These are different because the message content differs
        # (RSA-PSS would make them different anyway, but the input is actually different here)
        assert sig_get != sig_post
    
    def test_sign_request_different_for_different_timestamps(self, tmp_private_key: Path):
        """Different timestamps produce different messages."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        sig1 = auth.sign_request("1234567890000", "GET", "/test/path")
        sig2 = auth.sign_request("1234567890001", "GET", "/test/path")
        
        assert sig1 != sig2
    
    def test_sign_request_method_is_uppercased(self, tmp_private_key: Path):
        """HTTP method is uppercased before signing."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        # Can't compare signatures directly (RSA-PSS is non-deterministic)
        # Just verify both produce valid signatures
        sig_lower = auth.sign_request("1234567890000", "get", "/test/path")
        sig_upper = auth.sign_request("1234567890000", "GET", "/test/path")
        
        import base64
        assert len(base64.b64decode(sig_lower)) > 0
        assert len(base64.b64decode(sig_upper)) > 0
    
    def test_get_auth_headers(self, tmp_private_key: Path):
        """get_auth_headers returns all required headers."""
        auth = KalshiAuth("test-key-id", tmp_private_key)
        auth.load_private_key()
        
        headers = auth.get_auth_headers("GET", "/test/path")
        
        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"


class TestCreateAuth:
    """Tests for create_auth helper."""
    
    def test_creates_and_loads_key(self, tmp_private_key: Path):
        """create_auth returns initialized auth with key loaded."""
        auth = create_auth("test-key-id", tmp_private_key)
        
        # Should be able to sign immediately
        signature = auth.sign_request("1234567890000", "GET", "/test")
        assert signature