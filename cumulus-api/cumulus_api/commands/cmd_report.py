import argparse
import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone

import boto3
import dateparser
from cumulus_api.request import ApiClient
from cumulus_report import (
    CMRGranuleSource,
    GranuleInfo,
    GranuleSource,
    ReportGenerator,
    SearchOptions,
)
from sortedcontainers import SortedList

log = logging.getLogger(__name__)


HELP = r"""
This command creates a reconciliation report by querying granules from different
sources (e.g. Cumulus API, CMR) ingested over specific time period and comparing
the lists to find granules that are not present in all sources.

# Examples

The default is to create a report of all granules ingested within the last week
and print them to the console:

  cumulus report --dataset NISAR

To show only granules ingested in the last day and write the results to a CSV
file:

  cumulus report --dataset NISAR --start-time "yesterday" --csv-outfile out.csv

To show only granules ingested over a specific time period, write the results to
a CSV file, render timestamps in UTC, and use a bearer token for CMR
authentication to view hidden collections:

  cumulus report \
    --dataset NISAR \
    --start-time "2024-03-26T00:12:18.373139Z" \
    --end-time "2024-03-25T20:12:36.2-04:00" \
    --timezone 0
    --csv-outfile out.csv \
    --token <bearer-token>
"""


class CumulusApiGranuleSource(GranuleSource):
    def __init__(self, name: str, client: ApiClient, headers: dict = {}):
        super().__init__(name)
        self.client = client
        self.headers = headers

    def get_granules(self, options: SearchOptions) -> list[GranuleInfo]:
        granules = SortedList()

        params = {
            "fields": ",".join(
                [
                    "granuleId",
                    "status",
                    "timestamp",
                ]
            ),
        }
        if options.update_date:
            begin, end = options.update_date
            if begin:
                params["timestamp__from"] = int(begin.timestamp() * 1000)
            if end:
                params["timestamp__to"] = int(end.timestamp() * 1000)

        for response in self.client.paginate(
            method="GET",
            path="/granules",
            headers=self.headers,
            params=params,
        ):
            response_payload = response.json()
            status_code = response_payload["statusCode"]
            if status_code != 200:
                raise Exception(f"API returned a {status_code} status!")

            body = json.loads(response_payload["body"])

            granules.update(
                (
                    GranuleInfo(
                        granule_id=result["granuleId"],
                        update_date=datetime.fromtimestamp(
                            result["timestamp"] / 1000,
                            tz=timezone.utc,
                        ),
                        status=result["status"],
                    )
                    for result in body.get("results", ())
                )
            )

        return granules


def _timezone(text: str) -> timezone:
    """
    Argparser type for parsing a timezone
    """
    return timezone(timedelta(hours=int(text)))


_timezone.__name__ = "timezone"


def date(text: str) -> datetime:
    return dateparser.parse(
        text,
        settings={"RETURN_AS_TIMEZONE_AWARE": True},
    )


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_report = subparsers.add_parser(
        "report",
        epilog=HELP,
        help="generate an ingest report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser_report.add_argument(
        "--dataset",
        help="dataset to filter by. e.g 'NISAR'",
        required=True,
    )
    parser_report.add_argument(
        "--start-time",
        help="granule search start time (defaults to one week ago)",
        type=date,
        default=datetime.now(timezone.utc) - timedelta(days=7),
    )
    parser_report.add_argument(
        "--end-time",
        help="granule search end time",
        type=date,
    )
    parser_report.add_argument(
        "--timezone",
        help="timezone offset in hours for the generated report",
        type=_timezone,
    )
    parser_report.add_argument(
        "--csv-outfile",
        help="path for CSV report to be written",
        type=pathlib.Path,
    )
    parser_report.add_argument(
        "--token",
        help="EDL bearer token to authenticate with CMR",
    )
    parser_report.set_defaults(func=cmd_report)

    return parser_report


def cmd_report(args: argparse.Namespace):
    session = boto3.Session(profile_name=args.profile)
    client = session.client("lambda")

    stack_name = f"{args.deploy_name}-cumulus-{args.maturity}"
    function_name = f"{stack_name}-{args.lambda_name}"
    asf_search_config = {
        "prod": {},
        "test": {
            "asf_session_params": {
                "edl_host": "uat.urs.earthdata.nasa.gov",
                "cmr_host": "cmr.uat.earthdata.nasa.gov",
            },
            "asf_search_options_params": {"host": "cmr.uat.earthdata.nasa.gov"},
        },
        "int": {
            "asf_session_params": {
                "edl_host": "uat.urs.earthdata.nasa.gov",
                "cmr_host": "cmr.uat.earthdata.nasa.gov",
            },
            "asf_search_options_params": {"host": "cmr.uat.earthdata.nasa.gov"},
            "asf_search_params": {
                "provider": "ASFDEV",
            },
        },
        "dev": {
            "asf_session_params": {
                "edl_host": "uat.urs.earthdata.nasa.gov",
                "cmr_host": "cmr.uat.earthdata.nasa.gov",
            },
            "asf_search_options_params": {"host": "cmr.uat.earthdata.nasa.gov"},
            "asf_search_params": {
                "provider": "ASFDEV",
            },
        },
    }

    report_generator = ReportGenerator(
        name=stack_name,
        options=SearchOptions(
            platform=args.dataset,
            update_date=(args.start_time, args.end_time),
        ),
        tz=args.timezone,
        sources=[
            CumulusApiGranuleSource(
                "Cumulus",
                ApiClient(client, function_name),
                headers={"Cumulus-API-Version": args.cumulus_api_version},
            ),
            CMRGranuleSource(
                "CMR",
                asf_search_token=args.token,
                **asf_search_config[args.maturity],
            ),
        ],
    )

    if args.csv_outfile:
        with open(args.csv_outfile, "w", newline="") as f:
            report_generator.csv_report(f)
    else:
        report_generator.log_report()
