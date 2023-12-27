use gql_client::{Client, GraphQLError};
use lambda_http::{run, service_fn, Error, IntoResponse, Request, Response};
use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Serialize)]
pub struct Vars {
    repository_location_name: String,
    repository_name: String,
    job_name: String,
    run_config_data: String,
}

#[derive(Deserialize)]
pub struct ResponseData {
    #[serde(rename = "launchRun")]
    launch_run: LaunchRun,
}

#[derive(Serialize, Deserialize)]
pub struct LaunchRun {
    #[serde(rename = "__typename")]
    typename: String,
    run: Option<LaunchRunSuccess>,
}

#[derive(Serialize, Deserialize)]
pub struct LaunchRunSuccess {
    #[serde(rename = "runId")]
    run_id: String,
}

struct DagsterClient {
    client: Client,
}

impl DagsterClient {
    fn new(endpoint: String) -> Self {
        Self {
            client: Client::new(endpoint),
        }
    }
    async fn do_request(&self) -> Result<Option<ResponseData>, GraphQLError> {
        let query = r#"
mutation LaunchRunMutation(
  $repository_location_name: String!
  $repository_name: String!
  $job_name: String!
  $run_config_data: RunConfigData!
)
{
  launchRun(
    executionParams: {
      selector: {
        repositoryLocationName: $repository_location_name
        repositoryName: $repository_name
        jobName: $job_name
      }
      runConfigData: $run_config_data
    }
  ) {
    __typename
    ... on LaunchRunSuccess {
      run {
        runId
      }
    }
    ... on RunConfigValidationInvalid {
      errors {
        message
        reason
      }
    }
    ... on PythonError {
      message
    }
  }
}
   "#;
        let vars = Vars {
            repository_location_name: "tutorial".to_string(),
            repository_name: "__repository__".to_string(),
            job_name: "hackernews_job".to_string(),
            run_config_data:
                "{\"resources\":{\"io_manager\":{\"config\":{\"base_dir\":\"data\"}}}}".to_string(),
        };
        return self
            .client
            .query_with_vars::<ResponseData, Vars>(query, vars)
            .await;
    }
}

#[allow(dead_code)]
#[derive(Deserialize, Debug)]
struct LaunchRunPayload {
    job_name: String,
}

// Box<dyn StdError + Send + Sync>
// CustomError のすべてのフィールドが Send と Sync を実装していると CustomError も Send と Sync を実装することができる
// Result は、エラー型が From トレイトを実装している場合に ? 演算子をサポートする
#[derive(Debug, Serialize)]
struct CustomError {
    msg: String,
}

impl std::error::Error for CustomError {}
// 暗黙的に満たしているので不要ではある
unsafe impl Send for CustomError {}
unsafe impl Sync for CustomError {}

impl std::fmt::Display for CustomError {
    /// Display the error struct as a JSON string
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let err_as_json = json!(self).to_string();
        write!(f, "{}", err_as_json)
    }
}

async fn function_handler(event: Request) -> Result<impl IntoResponse, Error> {
    let endpoint = std::env::var("DAGSTER_ENDPOINT")?;
    let signiture = std::env::var("SIGNITURE")?;

    let sig = event
        .headers()
        .get("Signiture")
        .ok_or(CustomError {
            msg: "Not Authorized".to_string(),
        })?
        .to_str()?;
    if sig != signiture {
        tracing::error!("Signiture mismatch");
        return Err(Box::new(CustomError {
            msg: "Not Authorized".to_string(),
        }));
    }

    let client = DagsterClient::new(endpoint.clone());
    let data = client.do_request().await.map_err(|e| {
        tracing::error!("error: {:?}", e);
        CustomError { msg: e.to_string() }
    })?;

    let data: LaunchRunSuccess = match data {
        Some(data) => {
            if let Some(run) = data.launch_run.run {
                tracing::info!("launch a run successfully. run_id: {}", run.run_id);
                run
            } else {
                return Err(Box::new(CustomError {
                    msg: "Internal server error".to_string(),
                }));
            }
        }
        None => {
            return Err(Box::new(CustomError {
                msg: "Internal server error".to_string(),
            }));
        }
    };

    // Return something that implements IntoResponse.
    // It will be serialized to the right response event automatically by the runtime
    let resp = Response::builder()
        .status(200)
        .header("content-type", "application/json")
        .body(json!({"run_id":data.run_id }).to_string())
        .map_err(Box::new)?;
    Ok(resp)
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    // env_logger::builder().format_timestamp_nanos().init();
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        // disable printing the name of the module in every log line.
        .with_target(false)
        // disabling time is handy because CloudWatch will add the ingestion time.
        .without_time()
        .init();

    run(service_fn(function_handler)).await
}
