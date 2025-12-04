#!/usr/bin/env bash
# One-click MLOps deploy helper
# - Bootstraps CDK (idempotent)
# - Deploys all stacks in order
# - Optionally ingests sample data into the main Feature Group
# - Optionally triggers CodePipeline start

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

stack_status() {
    local stack="$1"
    aws cloudformation describe-stacks \
        --stack-name "$stack" \
        --query "Stacks[0].StackStatus" \
        --output text 2>/dev/null
}

wait_stack_clear() {
    local stack="$1"
    local status
    status="$(stack_status "$stack")" || true
    if [ -z "$status" ] || [ "$status" = "None" ]; then
        return 0
    fi

    case "$status" in
        DELETE_IN_PROGRESS|ROLLBACK_IN_PROGRESS|UPDATE_ROLLBACK_IN_PROGRESS)
            info "$stack is $status - waiting for deletion to finish..."
            # Poll manually to avoid failing when stack disappears mid-wait
            for _ in $(seq 1 60); do
                status="$(stack_status "$stack")" || true
                if [ -z "$status" ] || [ "$status" = "None" ]; then
                    info "$stack deletion completed."
                    return 0
                fi
                sleep 10
            done
            error "$stack still $status after 10 minutes. Please retry."
            exit 1
            ;;
        ROLLBACK_COMPLETE|ROLLBACK_FAILED|UPDATE_ROLLBACK_FAILED|UPDATE_ROLLBACK_COMPLETE|DELETE_FAILED)
            error "$stack is in terminal state ($status). Delete the stack manually then rerun."
            exit 1
            ;;
        *)
            return 0
            ;;
    esac
}

bucket_exists() {
    local bucket="$1"
    aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1
}

require_cmd() {
    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            error "Missing required command: $cmd"
            exit 1
        fi
    done
}

get_ctx() {
    local key="$1" default="$2"
    python - <<'PY' "$key" "$default" "$ROOT" 2>/dev/null || true
import json, pathlib, sys
key, default, root = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.loads(pathlib.Path(root, "cdk.json").read_text())
print(cfg.get("context", {}).get(key, default))
PY
}

get_output() {
    local stack="$1" key="$2"
    aws cloudformation describe-stacks \
        --stack-name "$stack" \
        --query "Stacks[0].Outputs[?OutputKey==\`$key\`].OutputValue" \
        --output text \
        --region "$AWS_REGION" 2>/dev/null | sed 's/[[:space:]]*$//'
}

AWS_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}"
[ -z "$AWS_REGION" ] && AWS_REGION="ap-northeast-2"

require_cmd python3 pip aws cdk

ACCOUNT_ID="$(aws sts get-caller-identity --query 'Account' --output text)"
info "Deploying with AWS account $ACCOUNT_ID in $AWS_REGION"

export CDK_DEFAULT_ACCOUNT="$ACCOUNT_ID"
export CDK_DEFAULT_REGION="$AWS_REGION"

if [ ! -d ".venv" ]; then
    info "Creating Python virtualenv (.venv)..."
    python3 -m venv .venv
fi
info "Activating virtualenv and installing requirements..."
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -r requirements.txt >/dev/null

# Resolve project/env to build bucket names
PROJECT_NAME="$(get_ctx "project_name" "my-mlops")"
ENV_NAME="$(get_ctx "env_name" "dev")"
BASE_PREFIX="${PROJECT_NAME}-${ENV_NAME}"
BASE_LOGS_BUCKET="${BASE_PREFIX}-logs"
BASE_ARTIFACTS_BUCKET="${BASE_PREFIX}-artifacts"
BASE_DATA_BUCKET="${BASE_PREFIX}-data"

# Dev MLOps stack uses different naming
DEV_PROJECT="${PROJECT_NAME}-dev2-v2"
DEV_ENV="main"
DEV_PREFIX="${DEV_PROJECT}-${DEV_ENV}"
DEV_LOGS_BUCKET="${DEV_PREFIX}-logs"
DEV_ARTIFACTS_BUCKET="${DEV_PREFIX}-artifacts"
DEV_DATA_BUCKET="${DEV_PREFIX}-data"

BASE_CTX=()
if bucket_exists "$BASE_LOGS_BUCKET" || bucket_exists "$BASE_ARTIFACTS_BUCKET" || bucket_exists "$BASE_DATA_BUCKET"; then
    info "Reusing existing base buckets ($BASE_PREFIX)"
    BASE_CTX=(-c use_existing_buckets=true \
              -c existing_logs_bucket_name="$BASE_LOGS_BUCKET" \
              -c existing_artifacts_bucket_name="$BASE_ARTIFACTS_BUCKET" \
              -c existing_data_bucket_name="$BASE_DATA_BUCKET")
fi

DEV_CTX=()
if bucket_exists "$DEV_LOGS_BUCKET" || bucket_exists "$DEV_ARTIFACTS_BUCKET" || bucket_exists "$DEV_DATA_BUCKET"; then
    info "Reusing existing dev buckets ($DEV_PREFIX)"
    DEV_CTX=(-c use_existing_buckets=true \
             -c existing_logs_bucket_name="$DEV_LOGS_BUCKET" \
             -c existing_artifacts_bucket_name="$DEV_ARTIFACTS_BUCKET" \
             -c existing_data_bucket_name="$DEV_DATA_BUCKET")
fi

if [ "${SKIP_BOOTSTRAP:-0}" != "1" ]; then
    info "Running cdk bootstrap (safe to rerun)..."
    cdk bootstrap "aws://$ACCOUNT_ID/$AWS_REGION"
else
    warn "Skipping cdk bootstrap (SKIP_BOOTSTRAP=1)"
fi

# Deploy only the primary pipeline stack by default
STACKS=(
    "My-mlops-BaseStack"
)

# Optional: override CodeStar connection via env CODESTAR_CONNECTION_ARN
CODESTAR_CONNECTION_ARN="${CODESTAR_CONNECTION_ARN:-}"

info "Deploying stacks in order..."
for stack in "${STACKS[@]}"; do
    info "Deploying $stack ..."
    wait_stack_clear "$stack"
    CTX_ARGS=()
    case "$stack" in
        "My-mlops-BaseStack")
            CTX_ARGS=("${BASE_CTX[@]}")
            if [ -n "$CODESTAR_CONNECTION_ARN" ]; then
                CTX_ARGS+=(-c use_codestar_connection=true -c codestar_connection_arn="$CODESTAR_CONNECTION_ARN")
                info "Using CodeStar connection override: $CODESTAR_CONNECTION_ARN"
            fi
            ;;
        "My-mlops-DevMLOpsStack")
            CTX_ARGS=("${DEV_CTX[@]}")
            ;;
    esac
    cdk deploy "$stack" --require-approval never "${CTX_ARGS[@]}"
done

info "Collecting stack outputs..."
BASE_DATA_BUCKET="$(get_output "My-mlops-BaseStack" "DataBucket")"
BASE_SM_EXEC_ROLE="$(get_output "My-mlops-BaseStack" "SmExecRoleArn")"
PIPELINE_NAME="$(get_output "My-mlops-BaseStack" "PipelineName")"

DEV_DATA_BUCKET="$(get_output "My-mlops-DevMLOpsStack" "DevDataBucket")"
DEV_SM_EXEC_ROLE="$(get_output "My-mlops-DevMLOpsStack" "DevSmExecRoleArn")"
DEV_PIPELINE_NAME="$(get_output "My-mlops-DevMLOpsStack" "DevPipelineName")"

FEATURE_GROUP_NAME="$(get_ctx "feature_group_name" "ad-click-feature-group")"
DATA_CSV="${DATA_CSV:-$ROOT/ad_click_dataset.csv}"

# Ensure the base dataset exists in the S3 data bucket for pipelines
ensure_dataset_s3() {
    local bucket="$1" csv="$2"
    local key="datasets/ad_click_dataset.csv"
    if [ -z "$bucket" ]; then
        warn "Data bucket not found; cannot upload dataset"
        return
    fi
    if [ ! -f "$csv" ]; then
        warn "Local dataset not found at $csv; skipping S3 upload"
        return
    fi
    if aws s3api head-object --bucket "$bucket" --key "$key" >/dev/null 2>&1; then
        info "Dataset already present at s3://$bucket/$key"
    else
        info "Uploading dataset to s3://$bucket/$key ..."
        aws s3 cp "$csv" "s3://$bucket/$key"
    fi
}

ensure_dataset_s3 "$BASE_DATA_BUCKET" "$DATA_CSV"

if [ "${SKIP_INGEST:-0}" != "1" ]; then
    if [ ! -f "$DATA_CSV" ]; then
        warn "Sample CSV not found at $DATA_CSV; skipping ingestion"
    elif [ -z "$BASE_DATA_BUCKET" ] || [ -z "$BASE_SM_EXEC_ROLE" ]; then
        warn "Data bucket or SM execution role output missing; skipping ingestion"
    else
        info "Ingesting sample data into Feature Store ($FEATURE_GROUP_NAME)..."
        DATA_BUCKET="$BASE_DATA_BUCKET" \
        SM_EXEC_ROLE_ARN="$BASE_SM_EXEC_ROLE" \
        FEATURE_GROUP_NAME="$FEATURE_GROUP_NAME" \
        AWS_REGION="$AWS_REGION" \
        python3 scripts/ingest_to_feature_store.py \
            --csv "$DATA_CSV" \
            --feature-group-name "$FEATURE_GROUP_NAME" \
            --data-bucket "$BASE_DATA_BUCKET" \
            --sm-exec-role-arn "$BASE_SM_EXEC_ROLE"
    fi
else
    warn "Skipping Feature Store ingestion (SKIP_INGEST=1)"
fi

if [ "${WITH_DEV_DATA:-0}" = "1" ]; then
    DEV_FG="ad-click-feature-group-dev"
    if [ -f "$DATA_CSV" ] && [ -n "$DEV_DATA_BUCKET" ] && [ -n "$DEV_SM_EXEC_ROLE" ]; then
        info "Ingesting sample data into dev Feature Store ($DEV_FG)..."
        DATA_BUCKET="$DEV_DATA_BUCKET" \
        SM_EXEC_ROLE_ARN="$DEV_SM_EXEC_ROLE" \
        FEATURE_GROUP_NAME="$DEV_FG" \
        AWS_REGION="$AWS_REGION" \
        python scripts/ingest_to_feature_store.py \
            --csv "$DATA_CSV" \
            --feature-group-name "$DEV_FG" \
            --data-bucket "$DEV_DATA_BUCKET" \
            --sm-exec-role-arn "$DEV_SM_EXEC_ROLE"
    else
        warn "Dev ingestion skipped (missing data bucket/role or CSV)"
    fi
fi

if [ "${SKIP_PIPELINE_START:-0}" != "1" ]; then
    if [ -n "$PIPELINE_NAME" ]; then
        info "Starting CodePipeline: $PIPELINE_NAME"
        aws codepipeline start-pipeline-execution \
            --name "$PIPELINE_NAME" \
            --region "$AWS_REGION" >/dev/null
    else
        warn "Pipeline name not found in outputs; skipping start"
    fi

    if [ -n "$DEV_PIPELINE_NAME" ]; then
        info "Starting dev CodePipeline: $DEV_PIPELINE_NAME"
        aws codepipeline start-pipeline-execution \
            --name "$DEV_PIPELINE_NAME" \
            --region "$AWS_REGION" >/dev/null
    fi
else
    warn "Skipping pipeline trigger (SKIP_PIPELINE_START=1)"
fi

echo ""
info "One-click deploy completed."
echo "Outputs:"
echo "  Base data bucket : ${BASE_DATA_BUCKET:-N/A}"
echo "  Base SM exec role: ${BASE_SM_EXEC_ROLE:-N/A}"
echo "  Pipeline (prod)  : ${PIPELINE_NAME:-N/A}"
echo "  Pipeline (dev)   : ${DEV_PIPELINE_NAME:-N/A}"
echo ""
info "Toggles:"
echo "  SKIP_BOOTSTRAP=1      skip cdk bootstrap"
echo "  SKIP_INGEST=1         skip Feature Store ingestion"
echo "  WITH_DEV_DATA=1       ingest sample data to dev Feature Store as well"
echo "  SKIP_PIPELINE_START=1 skip starting CodePipeline"
