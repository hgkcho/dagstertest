import os
from typing import List, Optional

from dagster import (
    AssetSelection,
    ConfigurableResource,
    DagsterRunStatus,
    Definitions,
    EnvVar,
    FilesystemIOManager,
    HookContext,
    RunStatusSensorContext,
    ScheduleDefinition,
    SensorResult,
    define_asset_job,
    load_assets_from_modules,
    run_status_sensor,
)
from dagster_duckdb_pandas import DuckDBPandasIOManager
from dagster_slack import SlackResource

from tutorial.resources import DataGeneratorResource

from . import assets

all_assets = load_assets_from_modules([assets])


class SlackCliet(ConfigurableResource):
    slack: SlackResource

    def post(
        self,
        context: RunStatusSensorContext,
        channel: str,
        text: str,
        webserver_base_url: Optional[str] = None,
    ):
        if webserver_base_url:
            text += (
                f"\n<{webserver_base_url}/runs/{context.dagster_run.run_id}|View in"
                " Dagster UI>"
            )

        self.slack.get_client().chat_postMessage(
            channel=channel,
            text=text,
            webserver_base_url="http://localhost:3000",
        )


def my_message_fn(context: HookContext) -> str:
    return f"Op {context.op} worked!"


# Addition: define a job that will materialize the assets
hackernews_job = define_asset_job(
    "hackernews_job",
    selection=AssetSelection.all(),
)


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    request_job=hackernews_job,
)
def report_status_sensor(context: RunStatusSensorContext, slack_client: SlackCliet):
    slack_client.post(
        context=context,
        channel="#random",
        text=f'Job "{context.dagster_run.job_name}" succeeded.',
        webserver_base_url="http://localhost:3000",
    )
    return SensorResult()


# Addition: a ScheduleDefinition the job it should run and a cron schedule of how frequently to run it
hackernews_schedule = ScheduleDefinition(
    job=hackernews_job,
    cron_schedule="0 * * * *",  # every hour
)

io_manager = FilesystemIOManager(
    base_dir="data",  # Path is built relative to where `dagster dev` is run
)

datagen = DataGeneratorResource(num_days=EnvVar.int("HACKERNEWS_NUM_DAYS_WINDOW"))

database_io_manager = DuckDBPandasIOManager(database="analytics.hackernews")


defs = Definitions(
    assets=all_assets,
    jobs=[
        hackernews_job,
    ],  # Addition: add the job to Definitions object (see below)
    schedules=[hackernews_schedule],
    resources={
        "io_manager": io_manager,
        "database_io_manager": database_io_manager,
        "hackernews_api": datagen,
        "slack": SlackResource(token=EnvVar("SLACK_TOKEN")),
        "slack_client": SlackCliet(slack=SlackResource(token=EnvVar("SLACK_TOKEN"))),
    },
    sensors=[report_status_sensor],
)
