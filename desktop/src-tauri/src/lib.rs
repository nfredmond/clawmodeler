use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::Manager;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct EngineResult {
    ok: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    json: Option<Value>,
    json_parse_error: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceArtifacts {
    workspace: String,
    run_id: String,
    manifest: Option<Value>,
    qa_report: Option<Value>,
    workflow_report: Option<Value>,
    report_markdown: Option<String>,
    files: Vec<String>,
    files_truncated: bool,
}

#[derive(Serialize)]
struct ArtifactResult {
    ok: bool,
    json: WorkspaceArtifacts,
}

fn repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("CLAWMODELER_REPO_ROOT") {
        let path = PathBuf::from(root);
        if path.exists() {
            return path;
        }
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or(manifest_dir)
}

fn sidecar_candidates(app: &tauri::AppHandle) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(engine_bin) = std::env::var("CLAWMODELER_ENGINE_BIN") {
        candidates.push(PathBuf::from(engine_bin));
    }

    let binary_name = format!("clawmodeler-engine{}", std::env::consts::EXE_SUFFIX);

    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join(&binary_name));
        candidates.push(resource_dir.join("binaries").join(&binary_name));
    }

    candidates.push(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("binaries")
            .join(&binary_name),
    );

    candidates
}

fn sidecar_path(app: &tauri::AppHandle) -> Option<PathBuf> {
    sidecar_candidates(app)
        .into_iter()
        .find(|path| path.is_file())
}

fn run_engine_args(app: &tauri::AppHandle, args: Vec<String>) -> Result<EngineResult, String> {
    if args.iter().any(|arg| arg.contains('\0')) {
        return Err("ClawModeler arguments must not contain NUL bytes.".to_string());
    }

    let output = if let Some(engine_path) = sidecar_path(app) {
        Command::new(engine_path)
            .args(args)
            .env("PYTHONUNBUFFERED", "1")
            .output()
    } else {
        Command::new("python3")
            .arg("-m")
            .arg("clawmodeler_engine")
            .args(args)
            .current_dir(repo_root())
            .env("PYTHONUNBUFFERED", "1")
            .output()
    }
    .map_err(|error| format!("failed to start clawmodeler-engine: {error}"))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();
    let (json, json_parse_error) = match serde_json::from_str(stdout.trim()) {
        Ok(value) => (Some(value), None),
        Err(error) => (None, Some(format!("{error}"))),
    };

    Ok(EngineResult {
        ok: output.status.success(),
        exit_code: output.status.code().unwrap_or(1),
        stdout,
        stderr,
        json,
        json_parse_error,
    })
}

#[tauri::command]
fn clawmodeler_doctor(app: tauri::AppHandle) -> Result<EngineResult, String> {
    run_engine_args(&app, vec!["doctor".into(), "--json".into()])
}

#[tauri::command]
fn clawmodeler_tools(app: tauri::AppHandle) -> Result<EngineResult, String> {
    run_engine_args(&app, vec!["tools".into(), "--json".into()])
}

#[tauri::command]
fn clawmodeler_run(app: tauri::AppHandle, args: Vec<String>) -> Result<EngineResult, String> {
    run_engine_args(&app, args)
}

#[tauri::command]
fn clawmodeler_chat(
    app: tauri::AppHandle,
    workspace: String,
    run_id: String,
    message: String,
    no_history: Option<bool>,
) -> Result<EngineResult, String> {
    let workspace = workspace.trim().to_string();
    let run_id = run_id.trim().to_string();
    if workspace.is_empty() {
        return Err("workspace is required".to_string());
    }
    if run_id.is_empty() {
        return Err("run_id is required".to_string());
    }
    if message.trim().is_empty() {
        return Err("message is required".to_string());
    }

    let mut args: Vec<String> = vec![
        "chat".into(),
        "--workspace".into(),
        workspace,
        "--run-id".into(),
        run_id,
        "--message".into(),
        message,
        "--json".into(),
    ];
    if no_history.unwrap_or(false) {
        args.push("--no-history".into());
    }
    run_engine_args(&app, args)
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn clawmodeler_what_if(
    app: tauri::AppHandle,
    workspace: String,
    base_run_id: String,
    new_run_id: String,
    weight_safety: Option<f64>,
    weight_equity: Option<f64>,
    weight_climate: Option<f64>,
    weight_feasibility: Option<f64>,
    reference_vmt_per_capita: Option<f64>,
    threshold_pct: Option<f64>,
    include_projects: Option<Vec<String>>,
    exclude_projects: Option<Vec<String>>,
    sensitivity_floor: Option<String>,
) -> Result<EngineResult, String> {
    let workspace = workspace.trim().to_string();
    let base_run_id = base_run_id.trim().to_string();
    let new_run_id = new_run_id.trim().to_string();
    if workspace.is_empty() {
        return Err("workspace is required".to_string());
    }
    if base_run_id.is_empty() {
        return Err("base_run_id is required".to_string());
    }
    if new_run_id.is_empty() {
        return Err("new_run_id is required".to_string());
    }
    if base_run_id == new_run_id {
        return Err("base_run_id and new_run_id must differ".to_string());
    }

    let weights = [
        weight_safety,
        weight_equity,
        weight_climate,
        weight_feasibility,
    ];
    let supplied = weights.iter().filter(|w| w.is_some()).count();
    if supplied != 0 && supplied != 4 {
        return Err("weights must be supplied together or not at all".to_string());
    }

    let mut args: Vec<String> = vec![
        "what-if".into(),
        "--workspace".into(),
        workspace,
        "--base-run-id".into(),
        base_run_id,
        "--new-run-id".into(),
        new_run_id,
        "--json".into(),
    ];
    if supplied == 4 {
        args.push("--weight-safety".into());
        args.push(format!("{}", weight_safety.unwrap()));
        args.push("--weight-equity".into());
        args.push(format!("{}", weight_equity.unwrap()));
        args.push("--weight-climate".into());
        args.push(format!("{}", weight_climate.unwrap()));
        args.push("--weight-feasibility".into());
        args.push(format!("{}", weight_feasibility.unwrap()));
    }
    if let Some(value) = reference_vmt_per_capita {
        args.push("--reference-vmt-per-capita".into());
        args.push(format!("{value}"));
    }
    if let Some(value) = threshold_pct {
        args.push("--threshold-pct".into());
        args.push(format!("{value}"));
    }
    for project_id in include_projects.unwrap_or_default() {
        let trimmed = project_id.trim().to_string();
        if !trimmed.is_empty() {
            args.push("--include-project".into());
            args.push(trimmed);
        }
    }
    for project_id in exclude_projects.unwrap_or_default() {
        let trimmed = project_id.trim().to_string();
        if !trimmed.is_empty() {
            args.push("--exclude-project".into());
            args.push(trimmed);
        }
    }
    if let Some(floor) = sensitivity_floor {
        let trimmed = floor.trim().to_string();
        if !trimmed.is_empty() {
            args.push("--sensitivity-floor".into());
            args.push(trimmed);
        }
    }

    run_engine_args(&app, args)
}

#[tauri::command]
fn clawmodeler_portfolio(app: tauri::AppHandle, workspace: String) -> Result<EngineResult, String> {
    let workspace = workspace.trim().to_string();
    if workspace.is_empty() {
        return Err("workspace is required".to_string());
    }
    run_engine_args(
        &app,
        vec![
            "portfolio".into(),
            "--workspace".into(),
            workspace,
            "--json".into(),
        ],
    )
}

#[tauri::command]
fn clawmodeler_workspace(workspace: String, run_id: String) -> Result<ArtifactResult, String> {
    let workspace_path = PathBuf::from(workspace.trim());
    if workspace_path.as_os_str().is_empty() {
        return Err("workspace is required".to_string());
    }

    let run_id = if run_id.trim().is_empty() {
        "demo".to_string()
    } else {
        run_id.trim().to_string()
    };
    let run_root = workspace_path.join("runs").join(&run_id);
    let reports_dir = workspace_path.join("reports");
    let (files, files_truncated) = list_files(&run_root);
    let artifacts = WorkspaceArtifacts {
        workspace: workspace_path.to_string_lossy().to_string(),
        run_id: run_id.clone(),
        manifest: read_json(run_root.join("manifest.json")),
        qa_report: read_json(run_root.join("qa_report.json")),
        workflow_report: read_json(run_root.join("workflow_report.json")),
        report_markdown: fs::read_to_string(reports_dir.join(format!("{run_id}_report.md"))).ok(),
        files,
        files_truncated,
    };

    Ok(ArtifactResult {
        ok: true,
        json: artifacts,
    })
}

fn read_json(path: PathBuf) -> Option<Value> {
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

const FILE_LIST_LIMIT: usize = 500;

fn list_files(root: &Path) -> (Vec<String>, bool) {
    let mut files = Vec::new();
    collect_files(root, &mut files);
    files.sort();
    let truncated = files.len() > FILE_LIST_LIMIT;
    files.truncate(FILE_LIST_LIMIT);
    (files, truncated)
}

fn collect_files(root: &Path, files: &mut Vec<String>) {
    if files.len() > FILE_LIST_LIMIT {
        return;
    }
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_files(&path, files);
        } else if path.is_file() {
            files.push(path.to_string_lossy().to_string());
        }
    }
}

pub fn run() {
    if let Err(error) = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            clawmodeler_doctor,
            clawmodeler_tools,
            clawmodeler_run,
            clawmodeler_workspace,
            clawmodeler_chat,
            clawmodeler_what_if,
            clawmodeler_portfolio
        ])
        .run(tauri::generate_context!())
    {
        eprintln!("ClawModeler desktop failed to start: {error}");
        std::process::exit(1);
    }
}
