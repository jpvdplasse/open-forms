#!/usr/bin/env python
from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import django
from django.db.models import Q

from tabulate import tabulate

SRC_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_DIR.resolve()))

type Row = tuple[str, int, int, int]


def report_api_group_usage() -> bool:
    """
    Query forms that have new logic evaluation enabled but inconsistent logic rule
    configuration.
    """
    from openforms.contrib.objects_api.models import ObjectsAPIGroupConfig
    from openforms.registrations.contrib.zgw_apis.models import ZGWApiGroupConfig

    def _scan_groups() -> Iterator[Row]:
        zgw = ZGWApiGroupConfig.objects.all()
        yield (
            "ZGW",
            zgw.count(),
            0,  # there are no legacy urls at this level
            zgw.exclude(catalogue_domain="").count(),
        )

        objects = ObjectsAPIGroupConfig.objects.all()
        yield (
            "Objects",
            objects.count(),
            objects.filter(
                ~Q(informatieobjecttype_submission_report="")
                | ~Q(informatieobjecttype_submission_csv="")
                | ~Q(informatieobjecttype_attachment="")
            ).count(),
            objects.exclude(catalogue_domain="").count(),
        )

    print(
        tabulate(
            _scan_groups(),
            headers=("Type", "# total", "# with legacy URLs", "# with catalogue"),
        )
    )

    return True


def main(skip_setup=False) -> bool:
    from openforms.setup import setup_env

    if not skip_setup:
        setup_env()
        django.setup()

    return report_api_group_usage()


if __name__ == "__main__":
    main()
