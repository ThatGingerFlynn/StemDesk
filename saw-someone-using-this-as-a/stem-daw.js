const audioContext = new AudioContext();
const tracksElement = document.querySelector("#tracks");
const template = document.querySelector("#trackTemplate");
const folderPicker = document.querySelector("#folderPicker");
const filePicker = document.querySelector("#filePicker");
const playButton = document.querySelector("#playButton");
const stopButton = document.querySelector("#stopButton");
const clearButton = document.querySelector("#clearButton");
const seekSlider = document.querySelector("#seekSlider");
const timeReadout = document.querySelector("#timeReadout");
const trackCount = document.querySelector("#trackCount");
const durationReadout = document.querySelector("#durationReadout");
const separatorForm = document.querySelector("#separatorForm");
const sourceAudio = document.querySelector("#sourceAudio");
const modelSelect = document.querySelector("#modelSelect");
const outputDir = document.querySelector("#outputDir");
const commandOverride = document.querySelector("#commandOverride");
const commandField = document.querySelector(".command-field");
const runSeparator = document.querySelector("#runSeparator");
const modelNote = document.querySelector("#modelNote");
const statusLog = document.querySelector("#statusLog");

let tracks = [];
let sources = [];
let modelCatalog = [];
let isPlaying = false;
let startedAt = 0;
let pausedAt = 0;
let animationFrame = 0;

const supportedAudio = /\.(aac|aif|aiff|flac|m4a|mp3|ogg|opus|wav|webm)$/i;
const apiBase = window.location.protocol === "file:" ? "http://127.0.0.1:8765" : "";
const defaultOutputDir = "/Users/plasmanf/Documents/Codex/2026-05-18/saw-someone-using-this-as-a/separated-output";

outputDir.value = defaultOutputDir;

folderPicker.addEventListener("change", (event) => loadFiles([...event.target.files]));
filePicker.addEventListener("change", (event) => loadFiles([...event.target.files]));
playButton.addEventListener("click", togglePlay);
stopButton.addEventListener("click", stop);
clearButton.addEventListener("click", clearSession);
separatorForm.addEventListener("submit", runLocalSeparation);
modelSelect.addEventListener("change", updateSelectedModel);
seekSlider.addEventListener("input", () => {
  pausedAt = Number(seekSlider.value) / 1000 * getDuration();
  updatePlayheads(pausedAt);
  updateReadout();
  if (isPlaying) {
    startPlayback(pausedAt);
  }
});

async function loadModelCatalog() {
  try {
    const response = await fetch(`${apiBase}/api/models`);
    if (!response.ok) throw new Error("Model catalog is not available.");
    const catalog = await response.json();
    modelCatalog = catalog.models || [];
    modelSelect.replaceChildren(...modelCatalog.map((model) => {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.name;
      return option;
    }));
    updateSelectedModel();
    setStatus("Ready. Choose an audio file and a local model.");
  } catch (error) {
    modelSelect.replaceChildren();
    runSeparator.disabled = true;
    setStatus("Start the local server to run models: python3 server.py");
    modelNote.textContent = "Stem viewing still works from folders/files. Separation needs the local server.";
  }
}

function updateSelectedModel() {
  const model = getSelectedModel();
  if (!model) return;
  commandOverride.value = model.runner === "manual" ? "" : model.command || "";
  commandOverride.placeholder = model.command || "Optional command template using {input_file} and {output_dir}";
  commandField.classList.toggle("is-hidden", model.runner !== "manual");
  modelNote.textContent = `${model.family} • ${model.stems}. ${model.notes || ""}`;
}

function getSelectedModel() {
  return modelCatalog.find((model) => model.id === modelSelect.value);
}

async function runLocalSeparation(event) {
  event.preventDefault();
  const audio = sourceAudio.files[0];
  if (!audio) {
    setStatus("Choose an input audio file first.");
    return;
  }

  stop();
  setBusy(true);
  runSeparator.disabled = true;
  setStatus("Running separation. This can take a while for real AI models...");

  try {
    const formData = new FormData();
    formData.append("audio", audio);
    formData.append("model_id", modelSelect.value);
    formData.append("output_dir", outputDir.value);
    formData.append("command", commandOverride.value);

    const response = await fetch(`${apiBase}/api/separate`, { method: "POST", body: formData });
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "Separation failed.");

    setStatus(`Created ${payload.stems.length} stem(s) in:\n${payload.session_dir}\n\nLoading stems...`);
    await loadStemUrls(payload.stems);
    setStatus(`Loaded ${payload.stems.length} stem(s).\n${payload.session_dir}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
    runSeparator.disabled = false;
  }
}

async function loadFiles(files) {
  const audioFiles = files
    .filter((file) => supportedAudio.test(file.name))
    .sort((a, b) => a.name.localeCompare(b.name));

  if (!audioFiles.length) return;

  stop();
  setBusy(true);

  try {
    const decoded = await Promise.all(audioFiles.map(decodeFile));
    tracks = decoded.map((track, index) => ({
      ...track,
      muted: false,
      solo: false,
      volume: 1,
      color: pickColor(index),
    }));
    renderTracks();
    updateTransportState();
  } finally {
    setBusy(false);
  }
}

async function loadStemUrls(stems) {
  const files = await Promise.all(stems.map(async (stem) => {
    const response = await fetch(`${apiBase}${stem.url}`);
    if (!response.ok) throw new Error(`Could not load ${stem.name}.`);
    const blob = await response.blob();
    return new File([blob], `${stem.name}.wav`, { type: blob.type || "audio/wav" });
  }));
  await loadFiles(files);
}

async function decodeFile(file) {
  const arrayBuffer = await file.arrayBuffer();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  const displayName = file.webkitRelativePath ? file.webkitRelativePath.split("/").pop() : file.name;
  return { file, name: cleanName(displayName), audioBuffer };
}

function renderTracks() {
  tracksElement.replaceChildren();

  if (!tracks.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<strong>No stems loaded</strong><span>Open a UVR output folder or add individual audio files.</span>";
    tracksElement.append(empty);
    return;
  }

  tracks.forEach((track, index) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const title = node.querySelector(".track-title");
    const mute = node.querySelector(".mute");
    const solo = node.querySelector(".solo");
    const volume = node.querySelector(".volume input");
    const canvas = node.querySelector("canvas");
    const lane = node.querySelector(".lane");

    title.textContent = track.name;
    mute.addEventListener("click", () => {
      track.muted = !track.muted;
      mute.classList.toggle("active", track.muted);
      applyMixState();
    });
    solo.addEventListener("click", () => {
      track.solo = !track.solo;
      solo.classList.toggle("active", track.solo);
      applyMixState();
    });
    volume.addEventListener("input", () => {
      track.volume = normalizeVolume(Number(volume.value));
      volume.value = track.volume;
      applyMixState();
    });
    volume.addEventListener("dblclick", () => {
      track.volume = 1;
      volume.value = track.volume;
      applyMixState();
    });
    lane.addEventListener("click", (event) => {
      const rect = lane.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      pausedAt = ratio * getDuration();
      seekSlider.value = Math.round(ratio * 1000);
      updatePlayheads(pausedAt);
      updateReadout();
      if (isPlaying) startPlayback(pausedAt);
    });

    track.element = node;
    track.canvas = canvas;
    tracksElement.append(node);
    drawWaveform(track, index);
  });

  window.addEventListener("resize", redrawWaveforms, { passive: true });
}

function togglePlay() {
  if (isPlaying) {
    pause();
  } else {
    audioContext.resume();
    startPlayback(pausedAt);
  }
}

function startPlayback(offset = 0) {
  stopSources();
  sources = tracks.flatMap((track) => {
    if (offset >= track.audioBuffer.duration) {
      track.gain = null;
      return [];
    }

    const source = audioContext.createBufferSource();
    const gain = audioContext.createGain();
    source.buffer = track.audioBuffer;
    source.connect(gain).connect(audioContext.destination);
    track.gain = gain;
    source.onended = () => {
      if (isPlaying && getCurrentTime() >= getDuration() - 0.05) stop();
    };
    source.start(0, offset);
    return [source];
  });

  startedAt = audioContext.currentTime - offset;
  isPlaying = true;
  playButton.textContent = "Pause";
  applyMixState();
  tick();
}

function pause() {
  pausedAt = getCurrentTime();
  stopSources();
  isPlaying = false;
  playButton.textContent = "Play";
  cancelAnimationFrame(animationFrame);
  updateReadout();
}

function stop() {
  stopSources();
  isPlaying = false;
  pausedAt = 0;
  playButton.textContent = "Play";
  seekSlider.value = 0;
  cancelAnimationFrame(animationFrame);
  updatePlayheads(0);
  updateReadout();
}

function stopSources() {
  sources.forEach((source) => {
    try {
      source.stop();
    } catch {
      // The source may already have ended.
    }
  });
  sources = [];
}

function clearSession() {
  stop();
  tracks = [];
  renderTracks();
  updateTransportState();
}

function applyMixState() {
  const hasSolo = tracks.some((track) => track.solo);
  tracks.forEach((track) => {
    if (!track.gain) return;
    const shouldPlay = hasSolo ? track.solo : !track.muted;
    track.gain.gain.value = shouldPlay ? track.volume : 0;
  });
}

function tick() {
  const currentTime = getCurrentTime();
  if (currentTime >= getDuration()) {
    stop();
    return;
  }
  const duration = getDuration();
  seekSlider.value = duration ? Math.round(currentTime / duration * 1000) : 0;
  updatePlayheads(currentTime);
  updateReadout();
  animationFrame = requestAnimationFrame(tick);
}

function updatePlayheads(time) {
  const duration = getDuration();
  const percent = duration ? clamp(time / duration, 0, 1) * 100 : 0;
  tracks.forEach((track) => {
    const playhead = track.element?.querySelector(".playhead");
    if (playhead) playhead.style.left = `${percent}%`;
  });
}

function updateReadout() {
  const current = isPlaying ? getCurrentTime() : pausedAt;
  timeReadout.textContent = `${formatTime(current)} / ${formatTime(getDuration())}`;
}

function updateTransportState() {
  const hasTracks = tracks.length > 0;
  playButton.disabled = !hasTracks;
  stopButton.disabled = !hasTracks;
  clearButton.disabled = !hasTracks;
  seekSlider.disabled = !hasTracks;
  trackCount.textContent = String(tracks.length);
  durationReadout.textContent = formatTime(getDuration());
  updateReadout();
}

function getCurrentTime() {
  return isPlaying ? audioContext.currentTime - startedAt : pausedAt;
}

function getDuration() {
  return tracks.reduce((duration, track) => Math.max(duration, track.audioBuffer.duration), 0);
}

function drawWaveform(track, index) {
  const canvas = track.canvas;
  const rect = canvas.getBoundingClientRect();
  const pixelRatio = window.devicePixelRatio || 1;
  const width = Math.max(320, Math.floor(rect.width * pixelRatio));
  const height = Math.max(110, Math.floor(rect.height * pixelRatio));
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d");
  const data = track.audioBuffer.getChannelData(0);
  const samplesPerPixel = Math.max(1, Math.floor(data.length / width));
  const center = height / 2;
  const scale = height * 0.42;

  context.clearRect(0, 0, width, height);
  context.fillStyle = track.color;

  for (let x = 0; x < width; x++) {
    let min = 1;
    let max = -1;
    const start = x * samplesPerPixel;
    const end = Math.min(start + samplesPerPixel, data.length);

    for (let i = start; i < end; i++) {
      const sample = data[i];
      if (sample < min) min = sample;
      if (sample > max) max = sample;
    }

    const top = center + min * scale;
    const bottom = center + max * scale;
    context.fillRect(x, top, 1, Math.max(1, bottom - top));
  }
}

function redrawWaveforms() {
  tracks.forEach(drawWaveform);
}

function setBusy(isBusy) {
  playButton.disabled = isBusy || !tracks.length;
  folderPicker.disabled = isBusy;
  filePicker.disabled = isBusy;
  sourceAudio.disabled = isBusy;
  modelSelect.disabled = isBusy;
  outputDir.disabled = isBusy;
  commandOverride.disabled = isBusy;
}

function setStatus(message) {
  statusLog.textContent = message;
}

function cleanName(name) {
  return name
    .replace(/\.[^.]+$/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatTime(seconds) {
  const safeSeconds = Math.max(0, seconds || 0);
  const minutes = Math.floor(safeSeconds / 60);
  const wholeSeconds = Math.floor(safeSeconds % 60);
  const millis = Math.floor((safeSeconds % 1) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

function pickColor(index) {
  const colors = ["#51a9ff", "#7fd3b6", "#f2c572", "#db8cff", "#ff8d70", "#a4d26a", "#65d6e8", "#f47aa4"];
  return colors[index % colors.length];
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeVolume(value) {
  return Math.abs(value - 1) <= 0.04 ? 1 : value;
}

function makeDemoTrack(name, frequency, index) {
  const duration = 4;
  const sampleRate = audioContext.sampleRate;
  const buffer = audioContext.createBuffer(1, duration * sampleRate, sampleRate);
  const data = buffer.getChannelData(0);

  for (let i = 0; i < data.length; i++) {
    const envelope = Math.min(1, i / 5000, (data.length - i) / 5000);
    const tone = Math.sin(2 * Math.PI * frequency * i / sampleRate);
    const overtone = Math.sin(2 * Math.PI * frequency * 1.5 * i / sampleRate) * 0.25;
    data[i] = (tone + overtone) * 0.35 * envelope;
  }

  return {
    file: null,
    name,
    audioBuffer: buffer,
    muted: false,
    solo: false,
    volume: 1,
    color: pickColor(index),
  };
}

function loadDemoSession() {
  tracks = [
    makeDemoTrack("1 06. Like a Fool (Instrumental)", 440, 0),
    makeDemoTrack("1 06. Like a Fool (Vocals)", 115, 1),
    makeDemoTrack("bass", 65, 2),
    makeDemoTrack("drums", 220, 3),
  ];
  renderTracks();
  updateTransportState();
}

updateTransportState();
loadModelCatalog();

if (new URLSearchParams(window.location.search).has("demo")) {
  loadDemoSession();
}
