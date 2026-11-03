"""Amazon Bedrock access shared by the AI features (name moderation and the ticketing agent).

Both use the Converse API, which has the same request shape for every model, so the model is just
an id passed through an environment variable. The client is created lazily and kept at module level:
importing this module costs nothing in tests and a warm Lambda container reuses the connection.
"""

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        import boto3
        from botocore.config import Config

        # The HTTP API cuts an integration off at 30 s, so a slow model call must fail before that.
        _cliente = boto3.client(
            "bedrock-runtime",
            config=Config(connect_timeout=3, read_timeout=20, retries={"max_attempts": 2, "mode": "standard"}),
        )
    return _cliente
