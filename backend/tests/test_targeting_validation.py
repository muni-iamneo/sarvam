"""Pure validation of operator call-targeting input."""

import pytest

from src.domain.targeting import TargetingError, validate_targeting


def test_valid_language_only_passes():
    validate_targeting("ta-IN", None, None)  # no raise


def test_valid_language_with_push_passes():
    validate_targeting("hi-IN", 7, 15.0)  # no raise


def test_unsupported_language_raises():
    with pytest.raises(TargetingError):
        validate_targeting("fr-FR", None, None)


def test_push_without_discount_raises():
    with pytest.raises(TargetingError):
        validate_targeting("ta-IN", 7, None)


def test_discount_out_of_range_raises():
    with pytest.raises(TargetingError):
        validate_targeting("ta-IN", 7, 0.0)
    with pytest.raises(TargetingError):
        validate_targeting("ta-IN", 7, 150.0)
