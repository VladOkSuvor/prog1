"""Тести для APIClient, зокрема логіки повторів (exponential backoff)."""

from unittest.mock import MagicMock, patch

import requests

from polymarket_ai.collectors.api_client import APIClient


def _ok_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestAPIClientGet:
    @patch("time.sleep", return_value=None)
    def test_returns_json_on_success(self, mock_sleep):
        client = APIClient("https://example.com")
        with patch.object(client.session, "get", return_value=_ok_response({"ok": True})):
            result = client.get("/markets")
        assert result == {"ok": True}

    @patch("time.sleep", return_value=None)
    def test_retries_on_timeout_then_succeeds(self, mock_sleep):
        client = APIClient("https://example.com", retries=3)
        with patch.object(
            client.session,
            "get",
            side_effect=[requests.exceptions.Timeout(), requests.exceptions.Timeout(), _ok_response({"ok": True})],
        ) as mock_get:
            result = client.get("/markets")
        assert result == {"ok": True}
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2  # спали між спробами 1->2 і 2->3

    @patch("time.sleep", return_value=None)
    def test_gives_up_after_max_retries(self, mock_sleep):
        client = APIClient("https://example.com", retries=3)
        with patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError()) as mock_get:
            result = client.get("/markets")
        assert result is None
        assert mock_get.call_count == 3

    @patch("time.sleep", return_value=None)
    def test_http_error_does_not_retry(self, mock_sleep):
        client = APIClient("https://example.com", retries=5)
        error_response = MagicMock()
        error_response.status_code = 404
        http_error = requests.exceptions.HTTPError(response=error_response)
        bad_response = MagicMock()
        bad_response.raise_for_status.side_effect = http_error

        with patch.object(client.session, "get", return_value=bad_response) as mock_get:
            result = client.get("/markets/does-not-exist")

        assert result is None
        assert mock_get.call_count == 1  # HTTP-помилки не повторюються
        mock_sleep.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_invalid_json_returns_none(self, mock_sleep):
        client = APIClient("https://example.com")
        bad_response = MagicMock()
        bad_response.status_code = 200
        bad_response.raise_for_status.return_value = None
        bad_response.json.side_effect = ValueError("bad json")

        with patch.object(client.session, "get", return_value=bad_response):
            result = client.get("/markets")

        assert result is None

    def test_close_closes_session(self):
        client = APIClient("https://example.com")
        with patch.object(client.session, "close") as mock_close:
            client.close()
        mock_close.assert_called_once()
