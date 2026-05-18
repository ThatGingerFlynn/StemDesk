# Stem Desk

Stem Desk is a local audio stem-separation tool and DAW-style player. It allows you to separate vocals, drums, bass, and other instruments from any audio file using high-quality AI models (like Demucs v4) and listen to them in a synchronized mixer.

## Features

- **Local Processing:** Your audio never leaves your computer.
- **AI-Powered:** Uses Demucs v4 for high-quality separation.
- **DAW-Style Player:** Play, mute, solo, and adjust volume for each stem in real-time.
- **Visual Waveforms:** View the waveforms of all separated tracks.
- **Extensible:** Easily add custom commands for UVR (Ultimate Vocal Remover) models or other CLI-based separators.

## Quick Start

The easiest way to run Stem Desk is using the provided launcher:

```bash
bash run.sh
```

This script will:
1. Check for dependencies.
2. Run the setup (if it's the first time).
3. Start the Stem Desk server.
4. Open the application in your default web browser at `http://127.0.0.1:8765/index.html`.

## Adding More Models

Stem Desk is designed to be extensible. You can add new models by editing the `model-catalog.json` file.

### UVR and Custom Models

If you have [audio-separator](https://github.com/Facelytical/audio-separator) or another UVR-compatible CLI installed, you can add it to the catalog.

Example entry for a UVR model:

```json
{
  "id": "uvr-mdx-kim-vocal-2",
  "name": "UVR MDX-Net Kim Vocal 2",
  "family": "UVR",
  "stems": "vocals + instrumental",
  "availability": "Requires audio-separator installed",
  "runner": "command",
  "command": "audio-separator {input_file} --model_filename MDX_Net_Kim_Vocal_2.onnx --output_dir {output_dir}",
  "notes": "Excellent vocal extractor."
}
```

### Command Templates

When defining a `command` in `model-catalog.json`, you can use the following placeholders:

- `{input_file}`: The full path to the uploaded input audio file.
- `{output_dir}`: The path to the session folder where outputs should be saved.

Stem Desk will automatically find any audio files generated in the `{output_dir}` and load them into the player.

## Manual Setup

If you prefer to run things manually:

1. **Install Dependencies:**
   ```bash
   bash setup-demucs.sh
   ```

2. **Start the Server:**
   ```bash
   python3 server.py --port 8765
   ```

3. **Access the UI:**
   Open `http://127.0.0.1:8765/index.html` in your browser.

## Configuration

- `server.py`: The backend server handling file uploads, separation process streaming, and audio serving.
- `model-catalog.json`: The list of available models and their command templates.
- `index.html`, `app.js`, `style.css`: The frontend DAW-style player.

## Automatic Cleanup

To save disk space, Stem Desk automatically deletes the uploaded input file after the separation process successfully completes. Only the separated stems are kept in the output directory.
