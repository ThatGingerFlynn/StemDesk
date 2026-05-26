from __future__ import annotations

import argparse
import logging
import subprocess
import tempfile
from pathlib import Path

from audio_separator.separator.separator import Separator


class LocalModelSeparator(Separator):
  def __init__(self, *, model_path: Path, config_path: Path, device: str = "auto", **kwargs):
    self.local_model_path = model_path.resolve()
    self.local_config_path = config_path.resolve()
    self.requested_device = device
    super().__init__(**kwargs)

  def setup_accelerated_inferencing_device(self):
    if self.requested_device == "auto":
      return super().setup_accelerated_inferencing_device()

    import onnxruntime as ort
    import torch

    system_info = self.get_system_info()
    self.check_ffmpeg_installed()
    self.log_onnxruntime_packages()
    self.torch_device_cpu = torch.device("cpu")
    providers = ort.get_available_providers()

    if self.requested_device == "cpu":
      self.logger.info("Device override selected: CPU")
      self.torch_device = self.torch_device_cpu
      self.onnx_execution_provider = ["CPUExecutionProvider"]
      return

    if self.requested_device == "mps":
      if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() and system_info.processor == "arm":
        self.logger.info("Device override selected: Apple MPS/CoreML")
        self.configure_mps(providers)
        return
      raise RuntimeError("Apple MPS is not available on this machine.")

    if self.requested_device == "cuda":
      if torch.cuda.is_available():
        self.logger.info("Device override selected: NVIDIA CUDA")
        self.configure_cuda(providers)
        return
      raise RuntimeError("CUDA is not available in this Python environment.")

    raise RuntimeError(f"Unknown device override: {self.requested_device}")

  def download_model_files(self, model_filename):
    return (
      self.local_model_path.name,
      "MDXC",
      self.local_model_path.stem,
      str(self.local_model_path),
      str(self.local_config_path),
    )

  def load_model_data_from_yaml(self, yaml_config_filename):
    model_data = super().load_model_data_from_yaml(yaml_config_filename)
    model_config = model_data.get("model", {})
    if isinstance(model_config, dict):
      for key in ("freqs_per_bands", "num_bands"):
        if key in model_config and key not in model_data:
          model_data[key] = model_config[key]
    if "freqs_per_bands" in model_data or "num_bands" in model_data:
      model_data["is_roformer"] = True
    return model_data


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Run a local ckpt/yaml model through audio-separator.")
  parser.add_argument("--input_file", required=True)
  parser.add_argument("--output_dir", required=True)
  parser.add_argument("--model_path", required=True)
  parser.add_argument("--config_path", required=True)
  parser.add_argument("--output_format", default="WAV")
  parser.add_argument("--log_level", default="info")
  parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="auto")
  parser.add_argument("--use_soundfile", action="store_true", default=True)
  return parser.parse_args()


def prepare_input_audio(input_file: Path, temp_dir: Path) -> Path:
  if input_file.suffix.lower() in {".wav", ".flac", ".aif", ".aiff"}:
    return input_file

  converted = temp_dir / f"{input_file.stem}-stemdesk-input.wav"
  print(f"Converting input audio to WAV for separator compatibility: {converted}", flush=True)
  subprocess.run(
    [
      "ffmpeg",
      "-y",
      "-hide_banner",
      "-loglevel",
      "error",
      "-i",
      str(input_file),
      "-vn",
      "-ac",
      "2",
      "-ar",
      "44100",
      str(converted),
    ],
    check=True,
  )
  return converted


def main() -> None:
  args = parse_args()
  model_path = Path(args.model_path)
  config_path = Path(args.config_path)
  input_file = Path(args.input_file)
  output_dir = Path(args.output_dir)

  if not model_path.exists():
    raise FileNotFoundError(f"Model checkpoint not found: {model_path}")
  if not config_path.exists():
    raise FileNotFoundError(f"Model YAML config not found: {config_path}")
  if not input_file.exists():
    raise FileNotFoundError(f"Input audio not found: {input_file}")

  with tempfile.TemporaryDirectory(prefix="stemdesk-audio-") as temp_dir:
    prepared_input = prepare_input_audio(input_file, Path(temp_dir))
    separator = LocalModelSeparator(
      model_path=model_path,
      config_path=config_path,
      device=args.device,
      log_level=getattr(logging, args.log_level.upper(), logging.INFO),
      model_file_dir=str(model_path.parent),
      output_dir=str(output_dir),
      output_format=args.output_format,
      use_soundfile=args.use_soundfile,
    )
    separator.load_model(model_filename=model_path.name)
    output_files = separator.separate(str(prepared_input))
    if not output_files:
      raise RuntimeError("audio-separator finished without producing any output stems.")
    print("Separation complete! Output file(s): " + " ".join(output_files), flush=True)


if __name__ == "__main__":
  main()
