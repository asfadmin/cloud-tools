import argparse
import os
import sys
import urllib.parse
from datetime import datetime
from hashlib import sha256
from urllib.parse import ParseResult

import boto3
import humanize
from aws_requests_auth.aws_auth import AWSRequestsAuth
from remotezip import RemoteZip


def url(value: str) -> ParseResult:
    return urllib.parse.urlparse(value)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--profile", help="AWS profile name")

    subparsers = parser.add_subparsers(
        title="command",
        required=True,
        # Without this, the 'required' option doesn't work
        dest="command"
    )

    parser_extract = subparsers.add_parser(
        "extract",
        aliases=("x", "ex",),
        help="Extract a member of an archive to stdout"
    )
    parser_extract.add_argument("url", help="URL of object to access", type=url)
    parser_extract.add_argument(
        "filename",
        help=(
            "File to extract from the archive. If none provided, list the "
            "archive contents"
        ),
        nargs="?"
    )
    parser_extract.set_defaults(func=cmd_extract)

    parser_list = subparsers.add_parser(
        "list",
        aliases="l",
        help="List the members of an archive"
    )
    parser_list.add_argument("url", help="URL of object to access", type=url)
    parser_list.set_defaults(func=cmd_list)

    return parser


def get_request_params(args: argparse.Namespace):
    parsed: ParseResult = args.url
    if parsed.scheme == "s3":
        session = boto3.Session(profile_name=args.profile)
        credentials = session.get_credentials().get_frozen_credentials()
        bucket = parsed.netloc
        key = parsed.path
        host = f"{bucket}.s3-{session.region_name}.amazonaws.com"
        url = f"https://{host}{key}"
        auth = AWSRequestsAuth(
            aws_access_key=credentials.access_key,
            aws_secret_access_key=credentials.secret_key,
            aws_token=credentials.token,
            aws_host=host,
            aws_region=session.region_name,
            aws_service="s3"
        )
        headers = {"x-amz-content-sha256": sha256(b"").hexdigest()}
    else:
        url = parsed.geturl()
        auth = None
        headers = None

    return url, auth, headers


def cmd_extract(args):
    url, auth, headers = get_request_params(args)

    with RemoteZip(url, auth=auth, headers=headers) as rz:
        with rz.open(args.filename) as f:
            with os.fdopen(sys.stdout.fileno(), "wb", closefd=False) as stdout:
                for data in f:
                    stdout.write(data)
                stdout.flush()


def cmd_list(args):
    url, auth, headers = get_request_params(args)

    with RemoteZip(url, auth=auth, headers=headers) as rz:
        lines = [
            (
                str(datetime(*zi.date_time)),
                humanize.naturalsize(zi.file_size, True),
                zi.filename
            )
            for zi in rz.infolist()
        ]
        max_size = max(len(file_size) for _, file_size, *_ in lines)
        for date, file_size, *rest in lines:
            print(date, f"{file_size:>{max_size}}", *rest)


def main():
    parser = get_parser()
    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
