import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from pydantic import ValidationError

from app.email import EmailSendError, SESEmailSender
from app.settings import Settings, validate_email
from app.templates import COPY, EmailMessage, render_email


def settings(**overrides):
    return Settings(
        _env_file=None,
        email_sender="notifications@telelink.test",
        app_url="http://localhost:5173",
        **overrides,
    )


@pytest.mark.parametrize("template", COPY)
def test_templates(template):
    message = render_email(template, "https://app.example.test/")
    assert message.subject == COPY[template][0]
    assert COPY[template][1] in message.text
    assert 'href="https://app.example.test/patient"' in message.html
    assert "https://app.example.test/patient" in message.text
    assert "\n" not in message.subject


def test_html_attribute_escaping():
    message = render_email("document_ready", 'https://app.example.test/a"<b>')
    assert "&quot;&lt;b&gt;" in message.html


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://example.test",
        "https://u:p@example.test",
        "https://example.test/?token=x",
        "https://example.test/#x",
        "https://example.test/\n",
        "/relative",
    ],
)
def test_bad_app_url(url):
    with pytest.raises(ValueError):
        render_email("booking_confirmed", url)


def test_unknown_template():
    with pytest.raises(ValueError):
        render_email("unknown", "https://example.test")


@pytest.mark.parametrize(
    "address",
    [
        "a@example.test,b@example.test",
        "Name <a@example.test>",
        "a@example.test\r\nBcc: victim@example.test",
        "",
        "missing-at",
        "x" * 255 + "@example.test",
    ],
)
def test_bad_address(address):
    with pytest.raises(ValueError):
        validate_email(address)


def test_deployed_settings():
    with pytest.raises(ValidationError):
        settings(environment="production")
    with pytest.raises(ValidationError):
        settings(environment="production", aws_endpoint_url="http://localhost:4566")


def client():
    return boto3.client(
        "ses",
        region_name="ap-southeast-1",
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )


def test_ses_request():
    ses = client()
    message = render_email("booking_confirmed", "http://localhost:5173")
    expected = {
        "Source": "notifications@telelink.test",
        "Destination": {"ToAddresses": ["patient@example.test"]},
        "Message": {
            "Subject": {"Data": message.subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": message.text, "Charset": "UTF-8"},
                "Html": {"Data": message.html, "Charset": "UTF-8"},
            },
        },
    }
    with Stubber(ses) as stub:
        stub.add_response("send_email", {"MessageId": "accepted-123"}, expected)
        assert (
            SESEmailSender(settings(), client=ses).send("patient@example.test", message)
            == "accepted-123"
        )
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("code", ["MessageRejected", "Throttling", "AccessDenied"])
def test_provider_failure_is_sanitized(code):
    ses = client()
    with Stubber(ses) as stub:
        stub.add_client_error(
            "send_email", service_error_code=code, service_message="private recipient@example.test"
        )
        with pytest.raises(EmailSendError) as error:
            SESEmailSender(settings(), client=ses).send(
                "patient@example.test", render_email("document_ready", "http://localhost:5173")
            )
        assert "private" not in str(error.value)
        assert "recipient" not in str(error.value)


@pytest.mark.parametrize("response", [{}, {"MessageId": ""}])
def test_missing_provider_id(response):
    class IncompleteSES:
        def send_email(self, **kwargs):
            return response

    with pytest.raises(EmailSendError):
        SESEmailSender(settings(), client=IncompleteSES()).send(
            "patient@example.test", render_email("document_ready", "http://localhost:5173")
        )


def test_header_injection_rejected_before_network():
    sender = SESEmailSender(settings(), client=object())
    with pytest.raises(ValueError):
        sender.send("patient@example.test", EmailMessage("hello\r\nBcc: x", "body", "body"))


def test_connection_failure_is_sanitized():
    class UnreachableSES:
        def send_email(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://private.example.test")

    with pytest.raises(EmailSendError) as error:
        SESEmailSender(settings(), client=UnreachableSES()).send(
            "patient@example.test", render_email("booking_confirmed", "http://localhost:5173")
        )
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "code,definitive,retryable",
    [
        ("Throttling", True, True),
        ("MessageRejected", True, False),
        ("ServiceUnavailable", False, False),
    ],
)
def test_acceptance_certainty(code, definitive, retryable):
    ses = client()
    with Stubber(ses) as stub:
        stub.add_client_error("send_email", service_error_code=code)
        with pytest.raises(EmailSendError) as error:
            SESEmailSender(settings(), client=ses).send(
                "patient@example.test", render_email("document_ready", "http://localhost:5173")
            )
        assert error.value.definitive == definitive and error.value.retryable == retryable


def test_ses_has_no_hidden_retries(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    sender = SESEmailSender(settings())
    try:
        assert sender.client.meta.config.retries["total_max_attempts"] == 1
    finally:
        sender.client.close()
