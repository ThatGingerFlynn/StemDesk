# Stem Desk

Stem Desk is a local stem-separation launcher plus DAW-style stem player.

## Start

```bash
python3 server.py --port 8765
```

Then open:

```text
http://127.0.0.1:8765/stem-daw.html
```

## Workflow

1. Choose an input audio file.
2. Choose a model preset.
3. Choose an output folder path.
4. Run separation.
5. Stem Desk creates a session folder, finds the generated audio stems, and loads them into the mixer.

## Model Presets

- `Demo local split`: built-in test path; creates fake instrumental/vocal stems.
- `Demucs v4 htdemucs_ft`: practical first free local test if Demucs is installed.
- `Demucs v4 htdemucs_6s`: free six-stem Demucs model if Demucs is installed.
- `UVR or audio-separator custom command`: command slot for UVR-compatible local CLIs.
- `MSST custom command`: command slot for local MSST configs/checkpoints.

## Demucs Setup

On this Mac, run:

```bash
bash setup-demucs.sh
```

That creates `.venv-demucs` and installs Demucs there. The two Demucs presets use that local environment.

Custom command templates can use:

```text
{input_file}
{output_dir}
```
