"""Patched Kalshi models with corrected validators.

The kalshi_python_async SDK has issues:
1. Incomplete status enum values - SDK only has 5, API returns 8
2. Some required fields that should be optional
3. Orderbook dollar fields expect strings but API returns ints

This module patches validators to handle API inconsistencies.

API Status Values: initialized, inactive, active, closed, determined, disputed, amended, finalized
SDK Status Values: initialized, active, closed, settled, determined (missing: inactive, disputed, amended, finalized)
"""

import kalshi_python_async.models.market as market_module
import kalshi_python_async.models.orderbook as orderbook_module


def patch_market_model():
    """Patch the Market model validators to fix SDK issues."""

    # Store original status value before validation
    original_model_validate = market_module.Market.model_validate

    @classmethod
    def patched_model_validate(cls, obj, *args, **kwargs):
        """Model validate with fixes for all API inconsistencies."""
        original_status = None

        if isinstance(obj, dict):
            # Save the original status value
            if 'status' in obj and obj['status']:
                original_status = obj['status']

                # Temporarily map unsupported statuses to valid ones for validation
                # We'll restore the real value after validation
                status_mapping = {
                    'finalized': 'settled',
                    'disputed': 'determined',
                    'amended': 'active',
                    'inactive': 'initialized',
                }
                if original_status in status_mapping:
                    obj['status'] = status_mapping[original_status]

            # Provide defaults for fields that should be optional but aren't
            if 'category' not in obj or obj.get('category') is None:
                obj['category'] = 'Unknown'
            if 'risk_limit_cents' not in obj or obj.get('risk_limit_cents') is None:
                obj['risk_limit_cents'] = 0

        # Validate with mapped status
        result = original_model_validate(obj, *args, **kwargs)

        # Restore the original status value so users see the real API status
        if original_status and original_status != result.status:
            # Use object.__setattr__ to bypass Pydantic's frozen/validation
            object.__setattr__(result, 'status', original_status)

        return result

    market_module.Market.model_validate = patched_model_validate

    # Patch Orderbook model to handle integer dollar values and None values
    original_orderbook_validate = orderbook_module.Orderbook.model_validate

    @classmethod
    def patched_orderbook_validate(cls, obj, *args, **kwargs):
        """Model validate with conversion of integer dollar values to strings and None to empty list."""
        if isinstance(obj, dict):
            # Handle yes_dollars: convert None to empty list, integers to strings
            if 'yes_dollars' in obj:
                if obj['yes_dollars'] is None:
                    obj['yes_dollars'] = []
                elif obj['yes_dollars']:
                    obj['yes_dollars'] = [
                        [str(item) if not isinstance(item, str) else item for item in pair]
                        for pair in obj['yes_dollars']
                    ]

            # Handle no_dollars: convert None to empty list, integers to strings
            if 'no_dollars' in obj:
                if obj['no_dollars'] is None:
                    obj['no_dollars'] = []
                elif obj['no_dollars']:
                    obj['no_dollars'] = [
                        [str(item) if not isinstance(item, str) else item for item in pair]
                        for pair in obj['no_dollars']
                    ]

        return original_orderbook_validate(obj, *args, **kwargs)

    orderbook_module.Orderbook.model_validate = patched_orderbook_validate
