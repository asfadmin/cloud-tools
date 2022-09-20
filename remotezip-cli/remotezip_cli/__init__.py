import argparse
import os
import sys
import urllib.parse
from hashlib import sha256

import boto3
from aws_requests_auth.aws_auth import AWSRequestsAuth
from remotezip import RemoteZip


def url(value: str) -> urllib.parse.ParseResult:
    return urllib.parse.urlparse(value)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument("url", help="URL of object to access", type=url)

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    parsed: urllib.parse.ParseResult = args.url
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

    with RemoteZip(url, auth=auth, headers=headers) as rz:
        if parsed.fragment:
            with rz.open(parsed.fragment) as f:
                with os.fdopen(sys.stdout.fileno(), "wb", closefd=False) as stdout:
                    for data in f:
                        stdout.write(data)
                    stdout.flush()
        else:
            for f in rz.namelist():
                print(f)
