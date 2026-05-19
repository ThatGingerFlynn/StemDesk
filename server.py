from __future__ import annotations

import argparse
from email import policy
from email.parser import BytesParser
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "model-catalog.json"
AUDIO_EXTENSIONS = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".webm"}


def load_catalog() -> dict:
  catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

  models_dir = ROOT / "models"
  if models_dir.exists():
    for subfolder in models_dir.iterdir():
      if subfolder.is_dir():
        ckpt_files = list(subfolder.glob("*.ckpt"))
        yaml_files = list(subfolder.glob("*.yaml"))

        if ckpt_files and yaml_files:
          # Use the first ckpt file found in the subfolder
          ckpt_path = ckpt_files[0]
          model_id = f"custom-{subfolder.name}"

          # Check if this model ID already exists to avoid duplicates
          if any(m["id"] == model_id for m in catalog["models"]):
            continue

          catalog["models"].append({
            "id": model_id,
            "name": f"Custom: {subfolder.name}",
            "family": "Roformer (Custom)",
            "stems": "vocals + instrumental",
            "availability": "Local custom model",
            "runner": "command",
            "command": f".venv-demucs/bin/python -m audio_separator.utils.cli {{input_file}} --model_filename {ckpt_path.name} --model_file_dir {shlex.quote(str(subfolder))} --output_dir {{output_dir}}",
            "notes": f"Custom Roformer model from models/{subfolder.name}"
          })

  return catalog


def safe_name(value: str) -> str:
  value = Path(value).stem or "audio"
  value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip()
  return value[:80] or "audio"


def ensure_writable_output(output_dir: Path) -> None:
  try:
    output_dir.mkdir(parents=True, exist_ok=True)
    test_file = output_dir / ".stemdesk-write-test"
    test_file.write_text("ok", encoding="utf-8")
    test_file.unlink()
  except PermissionError as exc:
    raise RuntimeError(
      "Stem Desk cannot write to that output folder. Choose a folder inside this project, "
      "or grant filesystem permission for the target folder."
    ) from exc


def audio_files_under(folder: Path) -> list[Path]:
  if not folder.exists():
    return []
  return sorted(
    [path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS],
    key=lambda path: path.name.lower(),
  )


def format_command(template: str, input_file: Path, output_dir: Path) -> list[str]:
  command = template.format(
    input_file=shlex.quote(str(input_file)),
    output_dir=shlex.quote(str(output_dir)),
  )
  parts = shlex.split(command)
  if parts and parts[0] == "python":
    parts[0] = sys.executable
  return parts


def parse_multipart_form(handler: SimpleHTTPRequestHandler) -> tuple[dict[str, str], dict[str, dict]]:
  content_type = handler.headers.get("Content-Type", "")
  content_length = int(handler.headers.get("Content-Length", "0"))
  body = handler.rfile.read(content_length)

  if content_type.startswith("application/x-www-form-urlencoded"):
    parsed = parse_qs(body.decode("utf-8"))
    return {key: values[0] for key, values in parsed.items()}, {}

  if not content_type.startswith("multipart/form-data"):
    raise RuntimeError("Expected a multipart form upload.")

  message_bytes = (
    f"Content-Type: {content_type}\r\n"
    "MIME-Version: 1.0\r\n\r\n"
  ).encode("utf-8") + body
  message = BytesParser(policy=policy.default).parsebytes(message_bytes)
  fields: dict[str, str] = {}
  files: dict[str, dict] = {}

  for part in message.iter_parts():
    name = part.get_param("name", header="content-disposition")
    if not name:
      continue
    filename = part.get_filename()
    payload = part.get_payload(decode=True) or b""
    if filename:
      files[name] = {"filename": filename, "data": payload}
    else:
      fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")

  return fields, files


def run_separator_stream(model: dict, input_file: Path, output_dir: Path, command_override: str = ""):
  template = command_override.strip() or model.get("command", "").strip()
  if not template:
    yield f"event: error\ndata: This model needs a command before it can run locally.\n\n"
    return

  output_dir.mkdir(parents=True, exist_ok=True)
  command = format_command(template, input_file, output_dir)
  executable = shutil.which(command[0])
  if executable is None and command[0] not in {"python", "python3"}:
    yield f"event: error\ndata: Could not find '{command[0]}' on PATH.\n\n"
    return

  yield f"event: log\ndata: $ {' '.join(shlex.quote(part) for part in command)}\n\n"

  env = os.environ.copy()
  env.setdefault("TORCH_HOME", str(ROOT / ".cache" / "torch"))
  env.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
  env["TORCHAUDIO_USE_TORCHCODEC"] = "0"
  # Set soundfile as the backend for torchaudio
  env["TORCHAUDIO_BACKEND"] = "soundfile"

  try:
    process = subprocess.Popen(
      command,
      cwd=str(ROOT),
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      env=env,
      bufsize=1,
      universal_newlines=True
    )

    full_output = []
    for line in process.stdout:
      full_output.append(line)
      yield f"event: log\ndata: {line.strip()}\n\n"

    process.wait()

    if "No module named demucs" in "".join(full_output):
      yield "event: error\ndata: Demucs is not installed for this Python. Install it with: python3 -m pip install demucs\n\n"
      return

    if process.returncode != 0:
      tail = "".join(full_output[-12:]).strip()
      yield f"event: error\ndata: Separator exited with code {process.returncode}.\n{tail}\n\n"
      return

    stems = [path for path in audio_files_under(output_dir) if "_input" not in path.parts]
    if not stems:
      yield "event: error\ndata: The separator finished, but no audio stems were found in the output folder.\n\n"
      return

    yield f"event: done\ndata: {json.dumps({'session_dir': str(output_dir.parent), 'stems': [{'name': p.stem, 'path': str(p), 'url': f'/api/audio?path={p}'} for p in stems if '_input' not in p.parts]})}\n\n"

    # Cleanup input file and its folder
    try:
      input_folder = input_file.parent
      if input_folder.name == "_input":
        shutil.rmtree(input_folder)
    except Exception as cleanup_exc:
      yield f"event: log\ndata: Warning: Could not delete input folder: {str(cleanup_exc)}\n\n"

  except Exception as exc:
    yield f"event: error\ndata: {str(exc)}\n\n"


class StemDeskHandler(SimpleHTTPRequestHandler):
  server_version = "StemDesk/0.1"

  def end_headers(self) -> None:
    self.send_header("Cache-Control", "no-store")
    super().end_headers()

  def do_GET(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/models":
      return self.send_json(load_catalog())
    if parsed.path == "/api/audio":
      return self.send_audio(parsed.query)
    if parsed.path == "/api/separate-stream":
      return self.handle_separate_stream(parsed.query)
    return super().do_GET()

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/separate":
      # We no longer handle multipart in the same way for streaming
      return self.handle_separate()
    self.send_error(404, "Unknown endpoint")

  def send_json(self, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def send_audio(self, query: str) -> None:
    params = parse_qs(query)
    raw_path = unquote(params.get("path", [""])[0])
    audio_path = Path(raw_path).expanduser().resolve()
    if not audio_path.exists() or audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
      self.send_error(404, "Audio file not found")
      return
    self.path = str(audio_path)
    return self.copy_audio_file(audio_path)

  def copy_audio_file(self, path: Path) -> None:
    content_type = "audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(path.stat().st_size))
    self.end_headers()
    with path.open("rb") as handle:
      shutil.copyfileobj(handle, self.wfile)

  def handle_separate(self) -> None:
    # This now just saves the file and returns a temporary file ID
    try:
      fields, files = parse_multipart_form(self)
      upload = files.get("audio")
      if upload is None or not upload.get("filename"):
        raise RuntimeError("Choose an input audio file.")

      temp_dir = ROOT / "temp_uploads"
      temp_dir.mkdir(parents=True, exist_ok=True)
      # Use a safe ID for the temporary file
      file_id = f"{int(time.time())}_{os.urandom(4).hex()}"
      temp_file = temp_dir / file_id
      with temp_file.open("wb") as handle:
        handle.write(upload["data"])

      self.send_json({
        "ok": True,
        "file_id": file_id,
        "filename": upload["filename"]
      })
    except Exception as exc:
      self.send_json({"ok": False, "error": str(exc)}, status=400)

  def handle_separate_stream(self, query: str) -> None:
    params = parse_qs(query)
    model_id = params.get("model_id", [""])[0]
    output_dir_text = params.get("output_dir", [""])[0].strip()
    command_override = params.get("command", [""])[0]
    file_id = params.get("file_id", [""])[0]
    original_filename = params.get("filename", ["audio.wav"])[0]

    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream")
    self.send_header("Cache-Control", "no-cache")
    self.send_header("Connection", "keep-alive")
    self.end_headers()

    temp_file_path = None
    try:
      if not model_id:
        raise RuntimeError("Choose a model first.")
      if not output_dir_text:
        raise RuntimeError("Choose or type an output directory.")

      # Security: Validate file_id and construct path only within temp_uploads
      if not file_id or not re.match(r"^[0-9]+_[0-9a-f]+$", file_id):
        raise RuntimeError("Invalid file ID.")

      temp_file_path = ROOT / "temp_uploads" / file_id
      if not temp_file_path.exists():
        raise RuntimeError("Input audio file not found on server.")

      catalog = load_catalog()
      model = next((item for item in catalog["models"] if item["id"] == model_id), None)
      if not model:
        raise RuntimeError("Unknown model.")

      output_dir = Path(output_dir_text).expanduser().resolve()
      ensure_writable_output(output_dir)

      session_dir = output_dir / f"{safe_name(original_filename)} - Stem Desk {time.strftime('%Y%m%d-%H%M%S')}"
      input_dir = session_dir / "_input"
      input_dir.mkdir(parents=True, exist_ok=True)

      input_file = input_dir / Path(original_filename).name
      shutil.move(str(temp_file_path), str(input_file))
      temp_file_path = None # Moved successfully

      for chunk in run_separator_stream(model, input_file, session_dir, command_override):
        try:
          self.wfile.write(chunk.encode("utf-8"))
          self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
          # Client disconnected, we should stop but keep the process running if it's already far along?
          # Actually, for simplicity, we just stop yielding
          break

    except Exception as exc:
      err_msg = f"event: error\ndata: {str(exc)}\n\n"
      self.wfile.write(err_msg.encode("utf-8"))
      self.wfile.flush()
    finally:
      if temp_file_path and temp_file_path.exists():
        try:
          temp_file_path.unlink()
        except:
          pass


def main() -> None:
  parser = argparse.ArgumentParser(description="Run Stem Desk locally.")
  parser.add_argument("--port", type=int, default=8765)
  args = parser.parse_args()
  os.chdir(ROOT)
  server = ThreadingHTTPServer(("127.0.0.1", args.port), StemDeskHandler)
  print(f"Stem Desk is running at http://127.0.0.1:{args.port}/index.html")
  server.serve_forever()


if __name__ == "__main__":
  main()
