from pydantic import ValidationError
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class PayloadValidator:
    """Validate incoming log payloads"""
    
    REQUIRED_FIELDS = [
        'conversation_id',
        'model',
        'provider',
        'status',
        'latency_ms',
    ]
    
    VALID_STATUSES = ['success', 'error', 'timeout']
    VALID_PROVIDERS = ['openai', 'anthropic', 'google', 'deepseek', 'grok']
    
    @staticmethod
    def validate(payload: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate payload
        Returns: (is_valid, error_message)
        """
        
        # Check required fields
        for field in PayloadValidator.REQUIRED_FIELDS:
            if field not in payload or payload[field] is None:
                return False, f"Missing required field: {field}"
        
        # Validate status
        if payload['status'] not in PayloadValidator.VALID_STATUSES:
            return False, f"Invalid status: {payload['status']}"
        
        # Validate provider
        if payload['provider'] not in PayloadValidator.VALID_PROVIDERS:
            return False, f"Invalid provider: {payload['provider']}"
        
        # Validate latency
        try:
            latency = int(payload['latency_ms'])\n            if latency < 0 or latency > 600000:  # Max 10 minutes\n                return False, f"Invalid latency: {latency}ms"\n        except (ValueError, TypeError):\n            return False, "latency_ms must be an integer"\n        \n        # Validate token counts\n        for field in ['input_tokens', 'output_tokens', 'total_tokens']:\n            if field in payload and payload[field] is not None:\n                try:\n                    tokens = int(payload[field])\n                    if tokens < 0:\n                        return False, f"Invalid {field}: cannot be negative"\n                except (ValueError, TypeError):\n                    return False, f"{field} must be an integer"\n        \n        # Validate cost\n        if 'cost_usd' in payload and payload['cost_usd'] is not None:\n            try:\n                cost = float(payload['cost_usd'])\n                if cost < 0:\n                    return False, "cost_usd cannot be negative"\n            except (ValueError, TypeError):\n                return False, "cost_usd must be a number"\n        \n        return True, ""\n    \n    @staticmethod\n    def sanitize(payload: Dict[str, Any]) -> Dict[str, Any]:\n        \"\"\"\n        Sanitize and normalize payload\n        \"\"\"\n        sanitized = payload.copy()\n        \n        # Set defaults\n        if 'input_tokens' not in sanitized:\n            sanitized['input_tokens'] = 0\n        if 'output_tokens' not in sanitized:\n            sanitized['output_tokens'] = 0\n        if 'total_tokens' not in sanitized:\n            sanitized['total_tokens'] = 0\n        if 'cost_usd' not in sanitized:\n            sanitized['cost_usd'] = 0.0\n        \n        # Truncate text fields\n        if 'request_preview' in sanitized and sanitized['request_preview']:\n            sanitized['request_preview'] = str(sanitized['request_preview'])[:1000]\n        if 'response_preview' in sanitized and sanitized['response_preview']:\n            sanitized['response_preview'] = str(sanitized['response_preview'])[:1000]\n        if 'error_message' in sanitized and sanitized['error_message']:\n            sanitized['error_message'] = str(sanitized['error_message'])[:500]\n        \n        return sanitized
