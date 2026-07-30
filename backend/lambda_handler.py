"""
AWS Lambda entrypoint for the FastAPI backend.

Adapts the ASGI app to the Lambda runtime via Mangum. Used only when the app is
deployed serverless (Lambda + Function URL behind CloudFront); the container
deployment keeps using uvicorn (see the __main__ block in backend/main.py).

lifespan="auto" lets FastAPI's startup event run on cold start so component
discovery (agents/workflows/triggers) populates the registries. There is no
in-process scheduler anywhere — the Claritty platform owns scheduling and fires
due triggers via POST /internal/run-due-triggers (see backend/main.py).

Configure the Lambda handler as: backend.lambda_handler.handler
"""

from mangum import Mangum

from backend.main import app

handler = Mangum(app, lifespan="auto")
