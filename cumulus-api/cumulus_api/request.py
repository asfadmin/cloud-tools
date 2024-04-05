import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ApiClient:
    client: Any
    function_name: str

    def request(
        self,
        method: str,
        path: str,
        body: str = "",
        headers: dict = {},
        params: dict = {},
    ):
        request = ApiRequest(
            path=path,
            body=body,
            method=method,
            headers=headers,
            params=params,
        )
        payload = json.dumps(request.payload)

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
        return ApiResponse(
            request=request,
            lambda_response=response,
        )


@dataclass
class ApiRequest:
    path: str
    body: str = ""
    method: str = "GET"
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    payload: dict = field(init=False)

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        self.payload = {
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


@dataclass
class ApiResponse:
    request: ApiRequest
    lambda_response: dict

    def json(self):
        return json.load(self.lambda_response["Payload"])
