import argparse
import inspect
import json
import os
import stat
import sys
import urllib.parse
import zipfile
from binascii import hexlify
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from importlib.metadata import Distribution
from platform import python_version
from typing import Any, Callable
from urllib.parse import ParseResult

import boto3
import humanize
from aws_requests_auth.aws_auth import AWSRequestsAuth
from remotezip import RemoteZip


def _get_version() -> str:
    name = "remotezip-cli"
    dist = Distribution.from_name(name)
    direct_url = json.loads(dist.read_text("direct_url.json"))
    editable = direct_url.get("dir_info", {}).get("editable", False)
    return (
        f"{name} {'(editable) ' if editable else ''}{dist.version} "
        f"on Python {python_version()}"
    )


def url(value: str) -> ParseResult:
    return urllib.parse.urlparse(value)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--version", action="version", version=_get_version())
    parser.add_argument("--profile", help="AWS profile name")

    subparsers = parser.add_subparsers(
        title="command",
        required=True,
        # Without this, the 'required' option doesn't work
        dest="command",
    )

    parser_extract = subparsers.add_parser(
        "extract",
        aliases=(
            "x",
            "ex",
        ),
        help="Extract a member of an archive to stdout",
    )
    parser_extract.add_argument("url", help="URL of object to access", type=url)
    parser_extract.add_argument(
        "filename",
        help=(
            "File to extract from the archive. If none provided, list the "
            "archive contents"
        ),
        nargs="?",
    )
    parser_extract.set_defaults(func=cmd_extract)

    parser_list = subparsers.add_parser(
        "list", aliases="l", help="List the members of an archive"
    )
    parser_list.add_argument("url", help="URL of object to access", type=url)
    zipinfo_group = parser_list.add_mutually_exclusive_group()
    zipinfo_group.add_argument(
        "--zipinfo",
        "-Z",
        help="Define the attributes to print out for each ZipInfo entry",
        nargs="*",
        action="extend",
        choices=[
            name
            for name, _ in inspect.getmembers(zipfile.ZipInfo, inspect.isdatadescriptor)
            if not name.startswith("_")
        ],
        default=None,
    )
    zipinfo_group.add_argument(
        "--compressed",
        "-c",
        help="Show details about the compressed contents of files",
        action="store_true",
    )
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
            aws_service="s3",
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

    def str_external_attr(val):
        hi = val >> 16
        lo = val & 0xFFFF

        res = []
        if hi:
            res.append(stat.filemode(hi))
        if lo:
            res.append(f"ext=0x{lo:x}")

        return " ".join(res)

    column_info = {
        "compress_type": ColumnInfo(
            "Comp. Type",
            "compress_type",
            lambda x: zipfile.compressor_names.get(x) or str(x),
        ),
        "compress_size": ColumnInfo(
            "Comp. Size",
            "compress_size",
            lambda x: humanize.naturalsize(x, True),
            align=">",
        ),
        "comment": ColumnInfo(
            "Comment", "comment", lambda x: x.decode(errors="replace")
        ),
        "create_system": ColumnInfo("Create System", "create_system"),
        "create_version": ColumnInfo("Create Version", "create_version"),
        "date_time": ColumnInfo("Timestamp", "date_time", lambda x: str(datetime(*x))),
        "external_attr": ColumnInfo(
            "File Attributes", "external_attr", str_external_attr
        ),
        "extra": ColumnInfo("Extra", "extra", lambda x: "0x" + hexlify(x).decode()),
        "extract_version": ColumnInfo(
            "PKZIP Version",
            "extract_version",
        ),
        "file_size": ColumnInfo(
            "Size", "file_size", lambda x: humanize.naturalsize(x, True), align=">"
        ),
        "filename": ColumnInfo("Name", "filename"),
        "flag_bits": ColumnInfo("Flag Bits", "flag_bits", bin, align=">"),
        "header_offset": ColumnInfo("Header Offset", "header_offset", align=">"),
        "internal_attr": ColumnInfo("Attributes", "internal_attr"),
        "orig_filename": ColumnInfo("Original Name", "orig_filename"),
        "reserved": ColumnInfo("Reserved", "reserved"),
        "volume": ColumnInfo("Volume", "volume"),
    }

    table = DisplayTable()
    if args.zipinfo is None:
        table.add_column(column_info["date_time"])
        table.add_column(column_info["file_size"])
        if args.compressed:
            table.add_column(column_info["compress_size"])
        table.add_column(column_info["filename"])
    else:
        for col_name in args.zipinfo:
            col_info = column_info.get(col_name) or ColumnInfo(col_name, col_name)
            table.add_column(col_info)

    with RemoteZip(url, auth=auth, headers=headers) as rz:
        for zipinfo in rz.infolist():
            table.add_row([col.get_value(zipinfo) for col in table.columns])

    print(f"Archive: {url}")

    table.display()

    print("-" * 10)
    print(f"{len(table.rows)} entries")


@dataclass
class ColumnInfo:
    name: str
    attr: str
    str_func: Callable[[Any], str] = str
    align: str = "<"
    max_size: int = 0

    def __post_init__(self):
        self.max_size = len(self.name)

    def get_value(self, zipinfo: zipfile.ZipInfo) -> str:
        return self.str_func(getattr(zipinfo, self.attr))


class DisplayTable:
    def __init__(self):
        self.columns = []
        self.rows = []

    def add_column(self, col: ColumnInfo):
        self.columns.append(col)

    def add_row(self, row):
        self.rows.append(row)
        for i, (col, col_info) in enumerate(zip(row, self.columns)):
            col_info.max_size = max(len(col), col_info.max_size)

    def display(self):
        print(*(f"{col.name:{col.align}{col.max_size}}" for col in self.columns))
        print(*("-" * col.max_size for col in self.columns))
        for line in self.rows:
            print(
                *(
                    f"{val:{col.align}{col.max_size}}"
                    for col, val in zip(self.columns, line)
                )
            )


def main():
    parser = get_parser()
    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()
