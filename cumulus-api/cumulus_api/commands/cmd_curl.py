import argparse
import http
import json
import logging
import sys
import urllib.parse
from typing import Tuple

import boto3
from cumulus_api.request import ApiClient

log = logging.getLogger(__name__)


def url(text: str):
    """
    Argparser type for parsing a URL
    """
    parse_result = urllib.parse.urlparse(text)
    if parse_result.query:
        params = urllib.parse.parse_qs(parse_result.query, strict_parsing=True)
        parse_result = parse_result._replace(params=params)

    return parse_result


def header(text: str) -> Tuple[str, str]:
    """
    Argparser type for parsing a header value
    """
    name, value = text.split(":")
    return name.strip(), value.strip()


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_curl = subparsers.add_parser(
        "curl",
        help="make curl style API requests",
    )
    parser_curl.add_argument(
        "url",
        help="URL to request. This can be just the path component",
        type=url,
    )

    parser_curl.add_argument(
        "-i",
        "--include",
        help="include the HTTP response headers in the output",
        action="store_true",
    )
    parser_curl.add_argument(
        "-X", "--request", help="set a custom request method to use", dest="method"
    )
    parser_curl.add_argument(
        "-H",
        "--header",
        help=(
            "extra header to include in the request when sending. Can be set "
            "multiple times"
        ),
        action="append",
        dest="headers",
        type=header,
        default=[],
    )
    parser_curl.add_argument(
        "-d",
        "--data",
        help="sends the specified data in a POST request to the HTTP server",
    )
    parser_curl.add_argument(
        "--pretty", help="pretty print output when possible", action="store_true"
    )
    parser_curl.set_defaults(func=cmd_curl)

    return parser_curl


def cmd_curl(args: argparse.Namespace):
    session = boto3.Session(profile_name=args.profile)
    client = session.client("lambda")

    log.debug("parsed url: %s", args.url)
    stack_name = args.url.netloc

    if stack_name:
        function_name = f"{stack_name}-{args.lambda_name}"
    else:
        function_name = f"{args.deploy_name}-cumulus-{args.maturity}-{args.lambda_name}"

    api_client = ApiClient(client, function_name)

    response = api_client.request(
        path=args.url.path,
        body=args.data,
        params=args.url.params,
        method=args.method or ("POST" if args.data else "GET"),
        headers={k: v for k, v in args.headers},
    )
    response_payload = response.json()

    body = response_payload["body"]
    status_code = response_payload["statusCode"]

    if args.include:
        status = http.HTTPStatus(status_code)
        request_context = response.request.payload["requestContext"]
        protocol = request_context["protocol"]
        request_id = request_context["requestId"]
        log.info("AWS Request Id: %s", request_id)
        log.info("%s %s %s", protocol, status.value, status.phrase)
        for k, v in response_payload["headers"].items():
            log.info("%s: %s", k, v)
        log.info("")

    if args.pretty:
        content_type = response_payload["headers"].get("content-type")
        try:
            if content_type.startswith("application/json"):
                body = pretty_print_json(body)
        except Exception as e:
            log.warning(
                "Could not pretty print malformed %s: %s",
                content_type,
                e,
            )

    log.info(body)

    if status_code >= 400:
        sys.exit(-1)


def pretty_print_json(text: str):
    return json.dumps(json.loads(text), indent=2)
