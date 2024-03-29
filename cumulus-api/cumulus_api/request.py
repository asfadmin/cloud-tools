import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ApiRequest:
    client: Any
    function_name: str
    path: str
    body: str = ""
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    payload: dict = None

    def get_api_gateway_payload(self) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "body": self.body,
            "headers": {
                "Host": "cumulus.app",
                "X-Forwarded-For": "127.0.0.1, 127.0.0.2",
                "X-Forwarded-Port": "443",
                "X-Forwarded-Proto": "https",
                **self.headers,
            },
            "httpMethod": self.method,
            "isBase64Encoded": False,
            "multiValueHeaders": {},
            "multiValueQueryStringParameters": self.params,
            "queryStringParameters": {},
            "path": self.path,
            "pathParameters": {"proxy": self.path},
            "requestContext": {
                "httpMethod": self.method,
                "path": self.path,
                "stage": "simulated",
                "resourcePath": "/{proxy+}",
                "accountId": "1",
                "apiId": "1",
                "identity": {},
                "protocol": "HTTP/1.1",
                "requestId": str(uuid.uuid4()),
                "requestTime": now.strftime("%d/%b/%Y:%M:%H:%S %z"),
                "resourceId": "123456",
            },
            "resource": "/{proxy+}",
            "stageVariables": {},
        }

    def invoke(self):
        self.payload = self.get_api_gateway_payload()
        payload = json.dumps(self.payload)

        log.debug(
            "Invoking function %s with payload\n%s",
            self.function_name,
            payload,
        )

        response = self.client.invoke(
            FunctionName=self.function_name,
            InvocationType="RequestResponse",
            Payload=payload,
        )
        return json.load(response["Payload"])
