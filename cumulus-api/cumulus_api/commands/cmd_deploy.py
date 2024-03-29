import argparse
import http
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import boto3
from cumulus_api.request import ApiRequest

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_deploy = subparsers.add_parser(
        "deploy",
        help="deploy providers/collections/rules",
    )
    parser_deploy.add_argument(
        "path",
        help=(
            "path to json file or directory containing "
            "providers/collections/rules. Subfolders and file types will be "
            "automatically discovered."
        ),
        type=Path,
    )
    parser_deploy.set_defaults(func=deploy_pcrs)

    return parser_deploy


def deploy_pcrs(args: argparse.Namespace):
    session = boto3.Session(profile_name=args.profile)
    client = session.client("lambda")
    caller_identity = session.client("sts").get_caller_identity()
    function_name = f"{args.deploy_name}-cumulus-{args.maturity}-{args.lambda_name}"

    variables = {
        "AWS_REGION": session.region_name,
        "AWS_ACCOUNT_ID": caller_identity.get("Account"),
        "DEPLOY_NAME": args.deploy_name,
        "MATURITY": args.maturity,
    }

    for path in discover_pcrs(args.path.resolve()):
        with open(path, "r") as f:
            text = substitute(f.read(), variables=variables)
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                log.debug("%s is not a valid json file", path)
                continue

        object_type = get_object_type(obj)
        object_id = get_object_id(obj)
        object_path = f"/{object_type}/{object_id}"
        if not object_type or not object_id:
            log.debug("%s is not a valid PCR", path)
            continue

        log.info("deploying %s from %s", object_path, path)

        response = ApiRequest(
            client,
            function_name=function_name,
            path=object_path,
            method="GET",
        ).invoke()

        if http.HTTPStatus(response["statusCode"]) == http.HTTPStatus.OK:
            # Need to perform an update
            log.info("%s already exists, updating...", object_path)
            response = ApiRequest(
                client,
                function_name=function_name,
                path=object_path,
                body=json.dumps(obj),
                method="PUT",
                headers={"Content-Type": "application/json"},
            ).invoke()
        else:
            response = ApiRequest(
                client,
                function_name=function_name,
                path=f"/{object_type}",
                body=json.dumps(obj),
                method="POST",
                headers={"Content-Type": "application/json"},
            ).invoke()

        status = http.HTTPStatus(response["statusCode"])
        log.info("API response %s %s", status.value, status.phrase)
        if status != http.HTTPStatus.OK:
            log.info("%s", response["body"])


def discover_pcrs(path: Path):
    if path.is_file() and path.suffix.lower() == ".json":
        yield path
    elif path.is_dir():
        for sub_path in sorted(path.iterdir()):
            yield from discover_pcrs(path / sub_path)


def get_object_type(obj: dict) -> Optional[str]:
    if "workflow" in obj:
        return "rules"
    elif "granuleId" in obj:
        return "collections"
    elif "id" in obj:
        return "providers"

    return None


def get_object_id(obj: dict) -> Optional[str]:
    object_id = obj.get("id") or obj.get("name") or None
    if not object_id:
        return None

    version = obj.get("version")
    if version:
        object_id = f"{object_id}/{version}"

    return object_id


def substitute(
    data: str,
    variables: dict = {},
    regex: re.Pattern = re.compile(r"\$[\w_]+", re.MULTILINE),
) -> str:
    def repl(match: re.Match) -> str:
        text = match.group()
        # Strip off the leading $
        name = text[1:]
        return os.getenv(name) or variables.get(name, text)

    return regex.sub(repl, data)
