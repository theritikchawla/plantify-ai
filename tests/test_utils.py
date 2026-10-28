"""Tests for utils.py (image checks and request throttling)."""

import io

import pytest
from PIL import Image

import config
import utils


def make_image_bytes(image_format="PNG", size=(100, 80), mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, (30, 160, 60)).save(buffer, format=image_format)
    return buffer.getvalue()


def test_png_is_converted_to_jpeg():
    prepared, mime_type = utils.prepare_image(make_image_bytes("PNG"))
    assert mime_type == "image/jpeg"
    assert Image.open(io.BytesIO(prepared)).format == "JPEG"


def test_transparent_png_is_accepted():
    prepared, _ = utils.prepare_image(make_image_bytes("PNG", mode="RGBA"))
    assert Image.open(io.BytesIO(prepared)).mode == "RGB"


def test_large_image_is_shrunk():
    big = make_image_bytes("PNG", size=(3000, 2000))
    prepared, _ = utils.prepare_image(big)
    width, height = Image.open(io.BytesIO(prepared)).size
    assert max(width, height) <= config.MAX_IMAGE_SIDE


def test_empty_file_is_rejected():
    with pytest.raises(utils.ImageValidationError):
        utils.prepare_image(b"")


def test_text_file_pretending_to_be_image_is_rejected():
    with pytest.raises(utils.ImageValidationError):
        utils.prepare_image(b"This is not an image at all")


def test_unsupported_format_is_rejected():
    with pytest.raises(utils.ImageValidationError):
        utils.prepare_image(make_image_bytes("GIF", mode="P"))


def test_oversized_file_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(utils.ImageValidationError):
        utils.prepare_image(make_image_bytes("PNG", size=(300, 300)))


def test_fingerprint_is_stable_and_different_for_different_images():
    assert utils.fingerprint(b"abc") == utils.fingerprint(b"abc")
    assert utils.fingerprint(b"abc") != utils.fingerprint(b"abd")


def test_cooldown_logic():
    assert utils.seconds_until_next_request(None, now=100, cooldown=10) == 0
    assert utils.seconds_until_next_request(95, now=100, cooldown=10) == 5
    assert utils.seconds_until_next_request(80, now=100, cooldown=10) == 0
