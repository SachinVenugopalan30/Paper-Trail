"""
GLM-OCR HTTP API Wrapper Module.

Provides a production-ready HTTP client for the GLM-OCR mlx-vlm server
running on localhost:8080. Supports base64 image encoding, configurable
max_tokens, exponential backoff retry logic, and comprehensive error handling.
"""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests


logger = logging.getLogger(__name__)


class GLMOCRClientError(Exception):
    """Base exception for GLM-OCR client errors."""
    pass


class GLMOCRServerError(GLMOCRClientError):
    """Exception raised when the OCR server returns an error response."""
    pass


class GLMOCRConnectionError(GLMOCRClientError):
    """Exception raised when unable to connect to the OCR server."""
    pass


class GLMOCRNonRetryableError(GLMOCRClientError):
    """Exception raised for 4xx client errors that should not be retried."""
    pass


def _encode_image_to_base64(image_path: str) -> str:
    """
    Encode an image file to base64 string.

    Args:
        image_path: Path to the image file

    Returns:
        Base64 encoded string of the image

    Raises:
        FileNotFoundError: If the image file does not exist
        IOError: If there's an error reading the file
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except IOError as e:
        raise IOError(f"Error reading image file {image_path}: {e}") from e


def _make_ocr_request(
    image_path: str,
    max_tokens: int,
    model: str = "",
    temperature: float = 0.7,
    timeout: int = 300
) -> dict:
    """
    Make a POST request to the GLM-OCR server.

    Args:
        image_path: Path to the image file to encode and send
        max_tokens: Maximum number of tokens to generate
        model: Model identifier to use
        temperature: Sampling temperature
        timeout: Request timeout in seconds

    Returns:
        JSON response from the server

    Raises:
        GLMOCRConnectionError: If unable to connect to server
        GLMOCRServerError: If server returns an error response
        requests.RequestException: For other request errors
    """
    # Encode image inside this call so the base64 string is freed on return
    image_b64 = _encode_image_to_base64(image_path)

    base = os.environ.get("OCR_API_BASE", "http://localhost:8080/v1")
    url = os.environ.get("GLM_OCR_URL", f"{base}/chat/completions")
    model = model or os.environ.get("GLM_OCR_MODEL", "zai-org/GLM-OCR")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": "Extract all text from this document"
                    }
                ]
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError as e:
        raise GLMOCRConnectionError(
            "Unable to connect to GLM-OCR server at localhost:8080. "
            "Ensure the mlx-vlm server is running."
        ) from e
    except requests.exceptions.Timeout as e:
        raise GLMOCRConnectionError(
            f"Request to GLM-OCR server timed out after {timeout} seconds"
        ) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        msg = f"GLM-OCR server returned error: {status} - {e.response.text}"
        if 400 <= status < 500:
            raise GLMOCRNonRetryableError(msg) from e
        raise GLMOCRServerError(msg) from e


def _extract_text_from_response(response: dict) -> str:
    """
    Extract the text content from the API response.

    Args:
        response: JSON response from the GLM-OCR server

    Returns:
        Extracted text content

    Raises:
        GLMOCRServerError: If response format is unexpected
    """
    try:
        if "choices" in response and len(response["choices"]) > 0:
            choice = response["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"].strip()
            elif "text" in choice:
                return choice["text"].strip()

        raise GLMOCRServerError(
            f"Unexpected response format from GLM-OCR server: {response}"
        )
    except (KeyError, IndexError, TypeError) as e:
        raise GLMOCRServerError(
            f"Failed to parse GLM-OCR response: {e}"
        ) from e


def extract_ocr(
    image_path: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    timeout: int = 300
) -> str:
    """
    Extract text from an image using the GLM-OCR HTTP API.

    This function sends the image to a local mlx-vlm server running on
    localhost:8080 and returns the extracted text. It includes retry logic
    with exponential backoff for transient failures.

    Args:
        image_path: Path to the image file (PNG, JPEG, etc.)
        max_tokens: Maximum number of tokens to generate (default: 4096)
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay between retries in seconds (default: 2.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        timeout: Request timeout in seconds (default: 300). 
                 Increase for large/complex images (600+ recommended)

    Returns:
        Extracted text content from the image

    Raises:
        FileNotFoundError: If the image file does not exist
        GLMOCRConnectionError: If unable to connect to the OCR server
        GLMOCRServerError: If the server returns an error after all retries
        IOError: If there's an error reading the image file

    Example:
        >>> text = extract_ocr("document_page_1.png", max_tokens=4096, timeout=300)
        >>> print(text)
        "Extracted text content..."
    """
    logger.info(f"Starting OCR extraction for: {image_path}")

    last_exception: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"OCR request attempt {attempt + 1}/{max_retries + 1}")

            response = _make_ocr_request(
                image_path=image_path,
                max_tokens=max_tokens,
                timeout=timeout
            )

            text = _extract_text_from_response(response)

            logger.info(
                f"OCR extraction successful for {image_path}: "
                f"{len(text)} characters extracted"
            )

            return text

        except GLMOCRNonRetryableError as e:
            logger.error(f"OCR request failed (non-retryable): {e}")
            raise

        except (GLMOCRConnectionError, GLMOCRServerError, requests.RequestException) as e:
            last_exception = e

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"OCR request failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay:.1f} seconds..."
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"OCR request failed after {max_retries + 1} attempts: {e}"
                )

    raise GLMOCRServerError(
        f"OCR extraction failed after {max_retries + 1} attempts: {last_exception}"
    ) from last_exception
