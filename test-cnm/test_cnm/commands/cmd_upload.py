import argparse
import os
from pathlib import Path
from typing import cast

from test_cnm.config import ConfigBasic
from test_cnm.metadata import Metadata
from test_cnm.uploader import Uploader


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_upload = subparsers.add_parser(
        "upload",
        help="Upload test files with appropriate metadata",
    )
    parser_upload.add_argument(
        "paths",
        help="Path to file or directory",
        nargs=argparse.ONE_OR_MORE,
        type=Path,
        metavar="path",
    )
    parser_upload.add_argument(
        "--collection",
        help="Collection name of this product",
        required=True,
    )
    parser_upload.add_argument(
        "--data-version",
        help=(
            "Data version for this product. If not set, the product will be "
            "uploaded without a data version."
        ),
    )
    parser_upload.add_argument(
        "--product",
        help=(
            "Product name of this product. If not set, the command will "
            "attempt to guess the product name from the file path."
        ),
    )
    parser_upload.add_argument(
        "--recursive",
        "-r",
        help="Upload a directory recursively",
        action="store_true",
        default=False,
    )
    parser_upload.set_defaults(
        func=cmd_upload,
        config_cls=ConfigBasic,
    )

    return parser_upload


def cmd_upload(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
):
    recursive: bool = args.recursive

    resolved_paths: list[Path] = []
    for path in cast(list[Path], args.paths):
        path = path.resolve()

        if not path.exists():
            parser.error(f"path '{path}' does not exist")

        resolved_paths.append(path)

    session = config.session()
    with Metadata(session, config.test_bucket) as metadata:
        uploader = Uploader(session, config.test_bucket, metadata)

        for path in resolved_paths:
            if not recursive:
                uploader.upload_file(
                    path,
                    collection=args.collection,
                    data_version=args.data_version,
                    product=args.product,
                )
            else:
                for root, _, files in os.walk(path):
                    root_path = Path(root)
                    for file in files:
                        if file == ".DS_Store":
                            continue

                        uploader.upload_file(
                            root_path / file,
                            collection=args.collection,
                            data_version=args.data_version,
                            product=args.product,
                        )
