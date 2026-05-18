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
  return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def safe_name(value: str) -> str:
  value = Path(value).stem or "audio"
  value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip()
  return value[:80] or "audio"


def write_demo_wav(path: Path, frequency: float, duration: float = 8.0, sample_rate: int = 44100) -> None:
  import math
  import struct

  frames = int(duration * sample_rate)
  path.parent.mkdir(parents=True, exist_ok=True)
  with wave.open(str(path), "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(2)
    handle.setframerate(sample_rate)
    for index in range(frames):
      envelope = min(1.0, index / 5000, (frames - index) / 5000)
      tone = math.sin(2 * math.pi * frequency * index / sample_rate)
      overtone = math.sin(2 * math.pi * frequency * 1.5 * index / sample_rate) * 0.25
      sample = int(max(-1.0, min(1.0, (tone + overtone) * 0.35 * envelope)) * 32767)
      handle.writeframes(struct.pack("<h", sample))


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


def run_separator(model: dict, input_file: Path, output_dir: Path, command_override: str = "") -> tuple[list[Path], list[str]]:
  logs: list[str] = []
  runner = model.get("runner")

  if runner == "demo":
    stem_dir = output_dir / f"{safe_name(input_file.name)} - demo stems"
    write_demo_wav(stem_dir / "instrumental.wav", 220)
    write_demo_wav(stem_dir / "vocals.wav", 440)
    logs.append("Created demo stems.")
    return audio_files_under(stem_dir), logs

  template = command_override.strip() or model.get("command", "").strip()
  if not template:
    raise RuntimeError("This model needs a command before it can run locally.")

  output_dir.mkdir(parents=True, exist_ok=True)
  command = format_command(template, input_file, output_dir)
  executable = shutil.which(command[0])
  if executable is None and command[0] not in {"python", "python3"}:
    raise RuntimeError(f"Could not find '{command[0]}' on PATH.")

  logs.append("$ " + " ".join(shlex.quote(part) for part in command))
  env = os.environ.copy()
  env.setdefault("TORCH_HOME", str(ROOT / ".cache" / "torch"))
  env.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))

  try:
    process = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, env=env)
  except FileNotFoundError as exc:
    raise RuntimeError(f"Could not find '{command[0]}'. Install it or update the command preset.") from exc
  if process.stdout:
    logs.append(process.stdout)
  if process.stderr:
    logs.append(process.stderr)
  combined_output = "\n".join([process.stdout or "", process.stderr or ""])
  if "No module named demucs" in combined_output:
    raise RuntimeError("Demucs is not installed for this Python. Install it with: python3 -m pip install demucs")
  if process.returncode != 0:
    tail = "\n".join(combined_output.strip().splitlines()[-12:])
    raise RuntimeError(f"Separator exited with code {process.returncode}.\n{tail}")

  stems = [path for path in audio_files_under(output_dir) if "_input" not in path.parts]
  if not stems:
    raise RuntimeError("The separator finished, but no audio stems were found in the output folder.")
  return stems, logs


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
    return super().do_GET()

  def do_POST(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/separate":
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
    try:
      fields, files = parse_multipart_form(self)
      model_id = fields.get("model_id", "")
      output_dir_text = fields.get("output_dir", "").strip()
      command_override = fields.get("command", "")
      upload = files.get("audio")

      if not model_id:
        raise RuntimeError("Choose a model first.")
      if not output_dir_text:
        raise RuntimeError("Choose or type an output directory.")
      if upload is None or not upload.get("filename"):
        raise RuntimeError("Choose an input audio file.")

      catalog = load_catalog()
      model = next((item for item in catalog["models"] if item["id"] == model_id), None)
      if not model:
        raise RuntimeError("Unknown model.")

      output_dir = Path(output_dir_text).expanduser().resolve()
      ensure_writable_output(output_dir)
      session_dir = output_dir / f"{safe_name(upload['filename'])} - Stem Desk {time.strftime('%Y%m%d-%H%M%S')}"
      input_dir = session_dir / "_input"
      input_dir.mkdir(parents=True, exist_ok=True)
      input_file = input_dir / Path(upload["filename"]).name
      with input_file.open("wb") as handle:
        handle.write(upload["data"])

      stems, logs = run_separator(model, input_file, session_dir, command_override)
      self.send_json({
        "ok": True,
        "session_dir": str(session_dir),
        "stems": [
          {"name": path.stem, "path": str(path), "url": f"/api/audio?path={path}"}
          for path in stems
          if "_input" not in path.parts
        ],
        "logs": logs,
      })
    except Exception as exc:
      self.send_json({"ok": False, "error": str(exc)}, status=400)


def main() -> None:
  parser = argparse.ArgumentParser(description="Run Stem Desk locally.")
  parser.add_argument("--port", type=int, default=8765)
  args = parser.parse_args()
  os.chdir(ROOT)
  server = ThreadingHTTPServer(("127.0.0.1", args.port), StemDeskHandler)
  print(f"Stem Desk is running at http://127.0.0.1:{args.port}/stem-daw.html")
  server.serve_forever()


if __name__ == "__main__":
  main()
