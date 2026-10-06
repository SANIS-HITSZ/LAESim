import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";

const byId = (id) => document.getElementById(id);
const numberValue = (id) => Number(byId(id).value);
const setValue = (id, value) => { byId(id).value = value ?? ""; };
const setText = (id, value) => { byId(id).textContent = value ?? ""; };
const setReferenceSource = (value) => {
  const target = byId("station-reference-source");
  const source = value || "未提供公开来源";
  const urlMatch = source.match(/https?:\/\/\S+/);
  target.replaceChildren(document.createTextNode(urlMatch ? source.replace(urlMatch[0], "").replace(/[；;\s]+$/, "") : source));
  if (!urlMatch) return;
  const link = document.createElement("a");
  link.className = "preset-source-link";
  link.href = urlMatch[0];
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = "查看公开参考资料";
  target.append(document.createElement("br"), link);
};
const RADIO_COLORS = [0x352a87, 0x1167a8, 0x17a673, 0xf0c541, 0xd14b33];

const state = {
  presets: null,
  downloads: {},
  sceneData: null,
  runId: null,
  radio: null,
  radioLayerVisible: true,
  selected: null,
  layers: {},
  routePlaying: false,
  routeProgress: 0,
  liveSync: false,
  liveSessionId: null,
  liveRouteSessionId: null,
  liveRoutes: null,
  livePosition: null,
  lastFrameTime: performance.now(),
  lastRadioQueryTime: 0,
  radioQueryInFlight: false,
  radioQueryPending: false,
  generationRequestId: 0,
  stationPresetOrigin: null,
  laesim: null,
  preflight: null,
  missionProcess: { status: "idle", running: false },
  configurationDirty: false,
  taskPickMode: null,
};

const STATION_FIELD_LABELS = {
  placement_family: "位置策略",
  density_per_km2: "站点密度",
  min_separation_m: "最小站间距",
  height_m: "天线高度",
  height_reference: "高度语义",
  reference_inter_site_distance_m: "参考站间距",
  random_offset_m: "随机偏移",
  power_dbm: "发射功率",
  carrier_frequency_hz: "载波频率",
  bandwidth_hz: "信道带宽",
  downtilt_deg: "下倾角",
  sectors: "扇区数量",
  sector_azimuths_deg: "扇区方位角",
  antenna_model: "天线模型",
};

const FUNCTION_TYPE_LABELS = {
  communication: "通信",
  low_altitude_communication: "低空通信增强",
  communication_and_sensing: "通信与感知",
  propagation_calibration: "传播模型校准",
};

const PARAMETER_STATUS_LABELS = {
  public_verified: "公开参数已核验",
  trial_specific: "仅适用于特定试点",
  simulation_proxy: "仿真代理值，需后续标定",
  unknown: "尚未确认",
};

const SCENARIO_LABELS = {
  suburban_corridor: "郊区航线",
  logistics_route: "物流航线",
  emergency_telemetry: "应急遥测",
  regular_urban: "普通城区",
  low_altitude_route: "低空航路",
  public_network_enhancement: "公网低空增强",
  scenic_area: "景区",
  critical_facility: "重点设施",
  port: "港口",
  low_altitude_governance: "低空治理",
  dense_hotspot: "密集热点",
  event_security: "活动安保",
  urban_macro_calibration: "城市宏站校准",
  urban_micro_street_canyon_calibration: "城市微站街谷校准",
  sensitivity_analysis: "敏感性分析",
};

const viewport = byId("viewport");
const canvas = byId("city-canvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene3d = new THREE.Scene();
scene3d.background = new THREE.Color(0xdce6ea);
scene3d.fog = new THREE.Fog(0xdce6ea, 900, 2500);
const camera = new THREE.PerspectiveCamera(43, 1, 0.5, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.screenSpacePanning = true;
controls.maxPolarAngle = Math.PI * 0.495;

scene3d.add(new THREE.HemisphereLight(0xeaf3f5, 0x6c7468, 2.1));
const sunlight = new THREE.DirectionalLight(0xfff5df, 2.2);
sunlight.position.set(500, 900, 300);
sunlight.castShadow = true;
sunlight.shadow.mapSize.set(2048, 2048);
scene3d.add(sunlight);

const contentRoot = new THREE.Group();
scene3d.add(contentRoot);
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let buildingMesh = null;
let buildingRecords = [];
let uavGroup = null;
let radioMesh = null;

function setStatus(message, error = false) {
  const element = byId("form-status");
  element.textContent = message;
  element.classList.toggle("is-error", error);
}

function setLaesimField(id, text, className = "") {
  const target = byId(id);
  target.textContent = text;
  target.className = className;
}

function runIdFromPath(path) {
  const parts = String(path || "").split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || "";
}

function setMissionGuidance(message = "") {
  const target = byId("laesim-guidance");
  target.textContent = message;
  target.hidden = !message;
}

function liveErrorMessage(live) {
  if (live.guidance) return live.guidance;
  if (live.error_code === "no_globally_connected_route" || String(live.error || "").includes("No globally connected route")) {
    return "当前高度和 SINR 门限下不存在连续可行航迹。请增加基站密度、使用更细的无线网格、调整任务点或重新评估门限。";
  }
  return live.error ? `任务失败：${live.error}` : "任务失败，请检查任务终端输出。";
}

function updateLaesimRunStatus(info = null) {
  state.laesim = info;
  if (!info || state.configurationDirty) {
    setLaesimField("laesim-run-id", state.configurationDirty ? "参数已修改，请重新生成" : "尚未生成", state.configurationDirty ? "is-warning" : "");
    setLaesimField("laesim-bundle-status", "未就绪");
    setLaesimField("laesim-import-status", "尚未导入");
    setLaesimField("laesim-match-status", "等待检查");
    byId("import-laesim").disabled = true;
    byId("open-laesim").disabled = true;
    updateMissionButtons();
    return;
  }
  setLaesimField("laesim-run-id", info.run_id || state.runId || "—");
  setLaesimField("laesim-bundle-status", info.bundle_ready ? "已就绪" : "缺少导入包", info.bundle_ready ? "is-ready" : "is-error");
  setLaesimField("laesim-import-status", info.imported ? (info.map_path || "已导入") : "尚未导入", info.imported ? "is-ready" : "is-warning");
  setLaesimField("laesim-match-status", info.import_matches ? "当前运行是最近一次导入记录" : (info.imported ? "已有旧导入记录，需要重新导入" : "导入后检查"), info.import_matches ? "is-ready" : "is-warning");
  const actionsAvailable = info.actions_available !== false;
  byId("import-laesim").disabled = !actionsAvailable || !info.bundle_ready;
  byId("open-laesim").disabled = !actionsAvailable || !info.import_matches;
  updateMissionButtons();
}

function updateMissionButtons() {
  const running = Boolean(state.missionProcess?.running);
  const ready = Boolean(
    state.runId
    && !state.configurationDirty
    && state.radio
    && state.preflight?.status === "ready"
    && state.laesim?.import_matches,
  );
  byId("start-laesim-mission").disabled = running || !ready;
  byId("stop-laesim-mission").disabled = !running;
}

function updateMissionProcess(info = { status: "idle", running: false }) {
  state.missionProcess = info;
  const labels = {
    idle: "未启动",
    running: "运行中",
    stopping: "正在安全停止",
    stopped: "已停止",
    complete: "已完成",
    error: `异常退出${Number.isInteger(info.return_code) ? `（代码 ${info.return_code}）` : ""}`,
  };
  const fieldClass = info.status === "error"
    ? "is-error"
    : (["running", "complete"].includes(info.status) ? "is-ready" : "");
  setLaesimField("laesim-process-status", labels[info.status] || info.status || "未知", fieldClass);
  const outputName = runIdFromPath(info.output_path);
  setText("laesim-process-output", outputName || "—");
  byId("laesim-process-output").title = info.output_path || "";
  updateMissionButtons();
}

function markConfigurationDirty() {
  if (!state.runId) return;
  state.configurationDirty = true;
  updateLaesimRunStatus(null);
  byId("run-preflight").disabled = true;
  renderPreflight(null);
}

async function runMissionProcessAction(action) {
  if (action === "start" && (!state.runId || state.configurationDirty)) return;
  const button = byId(action === "start" ? "start-laesim-mission" : "stop-laesim-mission");
  button.disabled = true;
  setStatus(action === "start" ? "正在启动 LAESim 任务…" : "正在请求无人机悬停并停止任务…");
  try {
    const response = await fetch(`/api/laesim/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action === "start" ? { run_id: state.runId } : {}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "LAESim 任务操作失败");
    updateMissionProcess(result);
    if (action === "start") {
      byId("laesim-sync").checked = true;
      toggleLaesimSync();
      setStatus("任务进程已启动，正在连接 UE/LAESim…");
    } else {
      setStatus("已发送安全停止请求，请等待任务状态更新");
    }
  } catch (error) {
    setStatus(error.message, true);
    updateMissionButtons();
  }
}

async function runLaesimAction(endpoint) {
  if (!state.runId || state.configurationDirty) return;
  const importing = endpoint.endsWith("/import");
  const button = byId(importing ? "import-laesim" : "open-laesim");
  button.disabled = true;
  setStatus(importing ? "正在导入 UE 场景，请勿打开 Unreal Editor…" : "正在打开 LAESim 场景…");
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: state.runId }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "LAESim 操作失败");
    updateLaesimRunStatus(result);
    setStatus(importing ? "LAESim 场景已更新，AirSim 配置已同步" : "LAESim 正在打开，请在 UE 中点击播放");
  } catch (error) {
    setStatus(error.message, true);
    updateLaesimRunStatus(state.laesim);
  }
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
        byId(item.getAttribute("aria-controls")).hidden = !active;
      });
      syncFeatureControls();
    });
  });
}

function populatePresets(catalog) {
  const citySelect = byId("city-preset");
  for (const [key, value] of Object.entries(catalog.city)) {
    citySelect.add(new Option(value.label, key));
  }
  citySelect.add(new Option("自定义", "custom"));
  citySelect.value = "dense_highrise_grid";

  const stationSelect = byId("station-preset");
  for (const [key, value] of Object.entries(catalog.base_station)) {
    stationSelect.add(new Option(value.label, key));
  }
  stationSelect.add(new Option("自定义", "custom"));
  stationSelect.value = "sub6_low_altitude_macro";
  const missionSelect = byId("mission-preset");
  for (const [key, value] of Object.entries(catalog.mission)) {
    missionSelect.add(new Option(value.label, key));
  }
  missionSelect.add(new Option("自定义", "custom"));
  missionSelect.value = "telemetry";
  applyCityPreset(citySelect.value);
  applyStationPreset(stationSelect.value);
  applyMissionPreset(missionSelect.value);
}

function applyMissionPreset(name) {
  if (name === "custom") {
    byId("mission-preset-description").textContent = "当前使用自定义实验约束；程序不会自动降低门限。";
    return;
  }
  const preset = state.presets.mission[name];
  setValue("minimum-sinr", preset.minimum_sinr_db);
  setValue("minimum-rss", preset.minimum_rss_dbm);
  setValue("maximum-outage", preset.maximum_outage_fraction);
  byId("mission-preset-description").textContent = preset.description;
}

function syncTaskPointControls() {
  const manual = byId("task-point-mode").value === "manual";
  byId("task-point-controls").setAttribute("aria-disabled", String(!manual));
  document.querySelectorAll("#task-point-controls input, #task-point-controls button").forEach((control) => {
    control.disabled = !manual;
  });
  if (!manual) cancelTaskPointPick();
}

function applyCityPreset(name) {
  if (name === "custom") return;
  const preset = state.presets.city[name];
  const building = preset.building;
  const roads = preset.roads;
  setValue("morphology", preset.morphology);
  setValue("size-x", 1000);
  setValue("size-y", 1000);
  setValue("road-spacing", roads.grid_spacing_m);
  setValue("road-width", roads.width_m);
  setValue("radial-count", roads.radial_count);
  setValue("ring-count", roads.ring_count);
  setValue("coverage", building.coverage_ratio);
  setValue("building-density", building.density_per_km2);
  setValue("height-distribution", building.height_distribution);
  setValue("height-min", building.height_min_m);
  setValue("height-max", building.height_max_m);
  setValue("height-mean", building.height_mean_m);
  setValue("height-std", building.height_std_m);
  setValue("foot-min-x", building.footprint_min_m[0]);
  setValue("foot-min-y", building.footprint_min_m[1]);
  setValue("foot-max-x", building.footprint_max_m[0]);
  setValue("foot-max-y", building.footprint_max_m[1]);
  setValue("separation", building.separation_m);
}

function applyStationPreset(name) {
  if (name === "custom") {
    const origin = state.presets.base_station[state.stationPresetOrigin];
    const modified = origin ? modifiedStationFields(origin.values) : [];
    byId("station-preset-description").textContent = origin
      ? `当前参数基于“${origin.label}”修改；导出时会保留来源预设和差异。`
      : "当前参数将作为无来源预设的自定义配置保存。";
    updateStationPresetMetadata(origin?.values, modified, true);
    return;
  }
  const preset = state.presets.base_station[name];
  const values = preset.values;
  state.stationPresetOrigin = name;
  byId("station-preset-description").textContent = preset.description;
  setValue("placement-family", values.placement_family);
  setValue("station-density", values.density_per_km2);
  setValue("station-separation", values.min_separation_m);
  setValue("station-height", values.height_m);
  setValue("height-reference", values.height_reference);
  setValue("reference-isd", values.reference_inter_site_distance_m);
  setValue("random-offset", values.random_offset_m);
  setValue("station-power", values.power_dbm);
  setValue("station-frequency", Number(values.carrier_frequency_hz) / 1e9);
  setValue("station-bandwidth", Number(values.bandwidth_hz) / 1e6);
  setValue("downtilt", values.downtilt_deg);
  setValue("sector-count", values.sectors);
  setValue("sector-azimuths", values.sector_azimuths_deg.join(", "));
  setValue("antenna-model", values.antenna_model);
  updateStationPresetMetadata(values, [], false);
  syncCarrierSummary();
}

function currentStationFields() {
  return {
    placement_family: byId("placement-family").value,
    density_per_km2: numberValue("station-density"),
    min_separation_m: numberValue("station-separation"),
    height_m: numberValue("station-height"),
    height_reference: byId("height-reference").value,
    reference_inter_site_distance_m: byId("reference-isd").value ? numberValue("reference-isd") : null,
    random_offset_m: numberValue("random-offset"),
    power_dbm: numberValue("station-power"),
    carrier_frequency_hz: numberValue("station-frequency") * 1e9,
    bandwidth_hz: numberValue("station-bandwidth") * 1e6,
    downtilt_deg: numberValue("downtilt"),
    sectors: numberValue("sector-count"),
    sector_azimuths_deg: byId("sector-azimuths").value.split(",").map((value) => Number(value.trim())).filter(Number.isFinite),
    antenna_model: byId("antenna-model").value,
  };
}

function modifiedStationFields(reference) {
  if (!reference) return [];
  const current = currentStationFields();
  return Object.keys(STATION_FIELD_LABELS).filter((key) => (
    JSON.stringify(current[key]) !== JSON.stringify(reference[key] ?? null)
  ));
}

function updateStationPresetMetadata(values, modifiedFields = [], customized = false) {
  const sourceId = values?.preset_id ?? "custom";
  setText("station-preset-id", customized ? `custom（来源：${sourceId}）` : `${sourceId} · v${values?.preset_version ?? "—"}`);
  setText("station-function-type", FUNCTION_TYPE_LABELS[values?.function_type] ?? values?.function_type ?? "—");
  setText("station-evidence-level", values?.source_evidence_level ? `${values.source_evidence_level} 级` : "—");
  setText("station-parameter-status", customized ? "自定义参数（按仿真代理管理）" : (PARAMETER_STATUS_LABELS[values?.parameter_status] ?? values?.parameter_status ?? "—"));
  setText("station-scenarios", values?.applicable_scenarios?.map((value) => SCENARIO_LABELS[value] ?? value).join("、") || "—");
  setReferenceSource(values?.reference_source);
  setText("station-modified-fields", modifiedFields.length ? modifiedFields.map((key) => STATION_FIELD_LABELS[key]).join("、") : "无");
  byId("station-modification-note").hidden = modifiedFields.length === 0;
}

function syncCarrierSummary() {
  byId("radio-carrier-summary").textContent = `使用基站配置：${numberValue("station-frequency").toFixed(1)} GHz · ${numberValue("station-bandwidth").toFixed(0)} MHz`;
}

function collectPayload({ includeRadio = false } = {}) {
  const azimuths = byId("sector-azimuths").value.split(",").map((value) => Number(value.trim())).filter(Number.isFinite);
  const sectors = numberValue("sector-count");
  if (azimuths.length !== sectors) throw new Error(`扇区数量是 ${sectors}，请填写 ${sectors} 个方位角。`);
  if (numberValue("height-max") < numberValue("height-min")) throw new Error("最高建筑高度不能小于最低高度。");
  if (numberValue("road-width") >= numberValue("road-spacing")) throw new Error("道路宽度必须小于道路间距。");
  const heightReference = byId("height-reference").value;
  const placement = byId("placement-family").value;
  if (placement === "street_grid" && heightReference !== "absolute_agl") {
    throw new Error("道路基站必须使用绝对离地高度。");
  }
  const presetKey = byId("station-preset").value;
  const sourceKey = presetKey === "custom" ? state.stationPresetOrigin : presetKey;
  const preset = state.presets.base_station[sourceKey];
  const modifiedFields = presetKey === "custom" ? modifiedStationFields(preset?.values) : [];
  const presetValues = preset?.values;
  const manualTask = byId("task-point-mode").value === "manual";
  const taskCoordinateIds = ["task-start-x", "task-start-y", "task-goal-x", "task-goal-y"];
  if (manualTask && taskCoordinateIds.some((id) => byId(id).value.trim() === "")) {
    throw new Error("手动任务模式需要完整填写起点和终点坐标。");
  }
  const start = [numberValue("task-start-x"), numberValue("task-start-y")];
  const goal = [numberValue("task-goal-x"), numberValue("task-goal-y")];
  if (manualTask && [...start, ...goal].some((value, index) => value < 0 || value > (index % 2 === 0 ? numberValue("size-x") : numberValue("size-y")))) {
    throw new Error("起点或终点超出当前城市范围。");
  }
  const minimumRss = byId("minimum-rss").value.trim();
  const task = {
    altitude_m: numberValue("task-altitude"),
    altitude_range_m: [35, 115],
    count: 1,
    selection_mode: manualTask ? "manual" : "auto",
    constraint_preset: byId("mission-preset").value,
    minimum_sinr_db: numberValue("minimum-sinr"),
    minimum_rss_dbm: minimumRss === "" ? null : Number(minimumRss),
    maximum_outage_fraction: numberValue("maximum-outage"),
  };
  if (manualTask) {
    task.start_xy_m = start;
    task.goal_xy_m = goal;
  }
  return {
    name: "interactive_city",
    seed: numberValue("seed"),
    city: {
      size_m: [numberValue("size-x"), numberValue("size-y")],
      morphology: byId("morphology").value,
      building: {
        profile: byId("city-preset").value,
        coverage_ratio: numberValue("coverage"),
        density_per_km2: numberValue("building-density"),
        height_distribution: byId("height-distribution").value,
        height_min_m: numberValue("height-min"),
        height_max_m: numberValue("height-max"),
        height_mean_m: numberValue("height-mean"),
        height_std_m: numberValue("height-std"),
        footprint_min_m: [numberValue("foot-min-x"), numberValue("foot-min-y")],
        footprint_max_m: [numberValue("foot-max-x"), numberValue("foot-max-y")],
        separation_m: numberValue("separation"),
      },
      roads: {
        grid_spacing_m: numberValue("road-spacing"),
        width_m: numberValue("road-width"),
        radial_count: numberValue("radial-count"),
        ring_count: numberValue("ring-count"),
      },
      base_stations: {
        preset_id: presetKey === "custom" ? "custom" : (presetValues?.preset_id ?? "custom"),
        preset_version: presetValues?.preset_version ?? "1.0.0",
        source_preset_id: presetValues?.preset_id ?? null,
        modified_fields: modifiedFields,
        deployment_profile: presetKey === "custom" ? `custom_from_${presetValues?.preset_id ?? "unspecified"}` : (presetValues?.deployment_profile ?? "custom_visualizer"),
        function_type: presetValues?.function_type ?? "communication",
        source_evidence_level: presetValues?.source_evidence_level ?? "D",
        parameter_status: presetKey === "custom" ? "simulation_proxy" : (presetValues?.parameter_status ?? "simulation_proxy"),
        applicable_scenarios: presetValues?.applicable_scenarios ?? [],
        placement_family: placement,
        density_per_km2: numberValue("station-density"),
        height_m: numberValue("station-height"),
        height_reference: heightReference,
        power_dbm: numberValue("station-power"),
        carrier_frequency_hz: numberValue("station-frequency") * 1e9,
        bandwidth_hz: numberValue("station-bandwidth") * 1e6,
        antenna_model: byId("antenna-model").value,
        polarization: presetValues?.polarization ?? "unknown",
        duplex_mode: presetValues?.duplex_mode ?? "unspecified",
        sensing_enabled: Boolean(presetValues?.sensing_enabled),
        sensing_waveform_class: presetValues?.sensing_waveform_class ?? null,
        reference_inter_site_distance_m: byId("reference-isd").value ? numberValue("reference-isd") : null,
        reference_source: presetValues?.reference_source ?? null,
        min_separation_m: numberValue("station-separation"),
        sectors,
        sector_azimuths_deg: azimuths,
        downtilt_deg: numberValue("downtilt"),
        random_offset_m: numberValue("random-offset"),
      },
      task,
      validation: { grid_resolution_m: 5, minimum_largest_component_fraction: 0.95 },
    },
    antenna_model: byId("antenna-model").value,
    radio: {
      enabled: includeRadio,
      quality: byId("radio-quality").value,
      height_m: numberValue("task-altitude"),
    },
  };
}

async function generateCity({ includeRadio = false } = {}) {
  let payload;
  try { payload = collectPayload({ includeRadio }); } catch (error) { setStatus(error.message, true); return; }
  const requestId = ++state.generationRequestId;
  const button = byId("generate-button");
  button.disabled = true;
  byId("loading-state").hidden = false;
  byId("loading-state").querySelector("span:last-child").textContent = payload.radio.enabled
    ? "正在生成城市并运行 Sionna RT…"
    : "正在生成并验证城市…";
  setStatus(payload.radio.enabled ? "正在运行 Sionna RT，请保持页面开启…" : "正在生成…");
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "生成失败");
    if (requestId !== state.generationRequestId) return;
    state.sceneData = result.scene;
    state.runId = result.run_id;
    state.radio = result.radio;
    state.downloads = result.downloads;
    state.configurationDirty = false;
    const generatedTask = result.scene.tasks?.[0];
    if (generatedTask) {
      setValue("task-start-x", Number(generatedTask.start_m[0]).toFixed(1));
      setValue("task-start-y", Number(generatedTask.start_m[1]).toFixed(1));
      setValue("task-goal-x", Number(generatedTask.goal_m[0]).toFixed(1));
      setValue("task-goal-y", Number(generatedTask.goal_m[1]).toFixed(1));
    }
    setValue("uav-altitude", result.scene.tasks?.[0]?.start_m?.[2] ?? numberValue("task-altitude"));
    updateLaesimRunStatus(result.laesim);
    renderScene(result.scene, result.base_station_manifest);
    updateDownloads();
    setRadioLayerAvailability(Boolean(result.radio));
    byId("run-preflight").disabled = !result.radio;
    renderPreflight(null);
    scheduleRadioQuery();
    setStatus(`${result.reused ? "已复用" : "已生成"} · ${result.run_id}${result.radio ? " · 无线地图就绪" : ""}`);
    if (result.radio) await runPreflight();
  } catch (error) {
    if (requestId === state.generationRequestId) setStatus(error.message, true);
  } finally {
    if (requestId === state.generationRequestId) {
      button.disabled = false;
      byId("loading-state").hidden = true;
    }
  }
}

function clearContent() {
  while (contentRoot.children.length) {
    const child = contentRoot.children.pop();
    child.traverse?.((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => {
        material.map?.dispose?.();
        material.dispose?.();
      });
      else {
        object.material?.map?.dispose?.();
        object.material?.dispose?.();
      }
    });
  }
  buildingMesh = null;
  buildingRecords = [];
  uavGroup = null;
  radioMesh = null;
  state.layers = {};
  state.liveRoutes = null;
  byId("route-comparison-panel").hidden = true;
  closeSelection();
}

function canonicalPosition(point) {
  return new THREE.Vector3(Number(point[0]), Number(point[2]), -Number(point[1]));
}

function renderScene(sceneData, stationManifest) {
  clearContent();
  const width = sceneData.bounds_m.maximum[0] - sceneData.bounds_m.minimum[0];
  const depth = sceneData.bounds_m.maximum[1] - sceneData.bounds_m.minimum[1];
  contentRoot.position.set(-width / 2, 0, depth / 2);

  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(width, depth),
    new THREE.MeshStandardMaterial({ color: 0xbcc5b8, roughness: 0.94 }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(width / 2, -0.3, -depth / 2);
  ground.receiveShadow = true;
  contentRoot.add(ground);

  const roads = new THREE.Group();
  roads.name = "roads";
  const roadMaterial = new THREE.MeshStandardMaterial({ color: 0x5e676a, roughness: 0.9 });
  for (const road of sceneData.roads) {
    if (road.axis === "ring") {
      const center = road.center_m;
      const radii = road.radius_m;
      const points = Array.from({ length: 128 }, (_, index) => {
        const angle = 2 * Math.PI * index / 128;
        return new THREE.Vector3(
          Number(center[0]) + Number(radii[0]) * Math.cos(angle),
          0,
          -(Number(center[1]) + Number(radii[1]) * Math.sin(angle)),
        );
      });
      const curve = new THREE.CatmullRomCurve3(points, true, "centripetal");
      roads.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 128, Number(road.width_m) / 2, 4, true), roadMaterial));
      continue;
    }
    const start = canonicalPosition(road.start_m);
    const end = canonicalPosition(road.end_m);
    const dx = end.x - start.x;
    const dz = end.z - start.z;
    const length = Math.hypot(dx, dz);
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(length, 0.25, Number(road.width_m)), roadMaterial);
    mesh.position.copy(start).add(end).multiplyScalar(0.5);
    mesh.position.y = 0;
    mesh.rotation.y = Math.atan2(Number(road.end_m[1]) - Number(road.start_m[1]), dx);
    roads.add(mesh);
  }
  contentRoot.add(roads);
  state.layers.roads = roads;

  const buildingGeometry = new THREE.BoxGeometry(1, 1, 1);
  const buildingMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.82, metalness: 0.02 });
  buildingMesh = new THREE.InstancedMesh(buildingGeometry, buildingMaterial, sceneData.buildings.length);
  buildingMesh.name = "buildings";
  buildingMesh.castShadow = true;
  buildingMesh.receiveShadow = true;
  const matrix = new THREE.Matrix4();
  const color = new THREE.Color();
  const maxHeight = Math.max(...sceneData.buildings.map((item) => Number(item.size_m[2])), 1);
  sceneData.buildings.forEach((building, index) => {
    const position = canonicalPosition(building.center_m);
    const scale = new THREE.Vector3(Number(building.size_m[0]), Number(building.size_m[2]), Number(building.size_m[1]));
    matrix.compose(position, new THREE.Quaternion(), scale);
    buildingMesh.setMatrixAt(index, matrix);
    const ratio = Number(building.size_m[2]) / maxHeight;
    color.set(ratio > 0.66 ? 0x59728a : ratio > 0.33 ? 0x71818d : 0x8b938d);
    buildingMesh.setColorAt(index, color);
    buildingRecords.push(building);
  });
  buildingMesh.instanceMatrix.needsUpdate = true;
  buildingMesh.instanceColor.needsUpdate = true;
  contentRoot.add(buildingMesh);
  state.layers.buildings = buildingMesh;

  const stations = new THREE.Group();
  stations.name = "stations";
  const sectors = new THREE.Group();
  sectors.name = "sectors";
  const poleMaterial = new THREE.MeshStandardMaterial({ color: 0x27363d, roughness: 0.55, metalness: 0.35 });
  const antennaMaterial = new THREE.MeshStandardMaterial({ color: 0xd58b24, roughness: 0.48 });
  for (const station of stationManifest.sites) {
    const position = canonicalPosition(station.position_m);
    const poleHeight = Math.max(2, position.y);
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 1.1, poleHeight, 8), poleMaterial);
    pole.position.set(position.x, poleHeight / 2, position.z);
    pole.userData.selection = { type: "基站", value: station };
    stations.add(pole);
    const head = new THREE.Mesh(new THREE.BoxGeometry(4, 3, 4), antennaMaterial);
    head.position.copy(position);
    head.userData.selection = { type: "基站", value: station };
    stations.add(head);
    for (const sector of station.sectors) {
      const radians = THREE.MathUtils.degToRad(Number(sector.azimuth_deg));
      const direction = new THREE.Vector3(Math.cos(radians), -Math.sin(THREE.MathUtils.degToRad(Number(sector.downtilt_deg))), -Math.sin(radians)).normalize();
      const arrow = new THREE.ArrowHelper(direction, position, 25, 0xd58b24, 4, 2.5);
      sectors.add(arrow);
    }
  }
  contentRoot.add(stations, sectors);
  state.layers.stations = stations;
  state.layers.sectors = sectors;

  const tasks = new THREE.Group();
  tasks.name = "tasks";
  for (const task of sceneData.tasks) {
    for (const [key, type, colorValue] of [["start_m", "任务起点", 0x278658], ["goal_m", "任务终点", 0xb9403b]]) {
      const marker = new THREE.Mesh(new THREE.SphereGeometry(4, 20, 12), new THREE.MeshStandardMaterial({ color: colorValue }));
      marker.position.copy(canonicalPosition(task[key]));
      marker.userData.selection = { type, value: { task_id: task.task_id, position_m: task[key] } };
      tasks.add(marker);
    }
  }
  contentRoot.add(tasks);
  state.layers.tasks = tasks;

  addUavAndTrajectory(sceneData);
  if (state.radio) addRadioLayer(state.radio);

  const borderPoints = [[0,0], [width,0], [width,depth], [0,depth], [0,0]].map(([x,y]) => new THREE.Vector3(x, 0.4, -y));
  const border = new THREE.Line(new THREE.BufferGeometry().setFromPoints(borderPoints), new THREE.LineBasicMaterial({ color: 0x33444a }));
  contentRoot.add(border);

  const stats = sceneData.metadata.statistics;
  byId("stat-buildings").textContent = sceneData.buildings.length.toLocaleString("zh-CN");
  byId("stat-sites").textContent = stationManifest.site_count.toLocaleString("zh-CN");
  byId("stat-sectors").textContent = stationManifest.sector_count.toLocaleString("zh-CN");
  byId("stat-coverage").textContent = `${(Number(stats.footprint_coverage_ratio) * 100).toFixed(1)}%`;
  resetCamera(width, depth, maxHeight);
  applyLayerVisibility();
  updateUavPosition(false);
}

function addUavAndTrajectory(sceneData) {
  const task = sceneData.tasks[0];
  if (!task) return;
  const altitude = numberValue("uav-altitude");
  const start = [Number(task.start_m[0]), Number(task.start_m[1]), altitude];
  const goal = [Number(task.goal_m[0]), Number(task.goal_m[1]), altitude];
  const trajectory = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([canonicalPosition(start), canonicalPosition(goal)]),
    new THREE.LineDashedMaterial({ color: 0x176a7d, dashSize: 12, gapSize: 7 }),
  );
  trajectory.computeLineDistances();
  contentRoot.add(trajectory);
  state.layers.trajectory = trajectory;

  uavGroup = new THREE.Group();
  uavGroup.name = "uav";
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0xf3f5f5, roughness: 0.45, metalness: 0.35 });
  const accentMaterial = new THREE.MeshStandardMaterial({ color: 0x176a7d, roughness: 0.4 });
  const rotorMaterial = new THREE.MeshStandardMaterial({ color: 0x26343a, roughness: 0.5, metalness: 0.4 });
  const body = new THREE.Mesh(new THREE.SphereGeometry(2.1, 16, 10), accentMaterial);
  body.scale.set(1.4, 0.55, 1);
  uavGroup.add(body);
  for (const angle of [Math.PI / 4, -Math.PI / 4]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(11, 0.45, 0.65), bodyMaterial);
    arm.rotation.y = angle;
    uavGroup.add(arm);
  }
  for (const [x, z] of [[4, 4], [4, -4], [-4, 4], [-4, -4]]) {
    const rotor = new THREE.Mesh(new THREE.CylinderGeometry(2.4, 2.4, 0.18, 20), rotorMaterial);
    rotor.position.set(x, 0.45, z);
    uavGroup.add(rotor);
  }
  uavGroup.userData.selection = { type: "虚拟无人机", value: { task_id: task.task_id, position_m: start } };
  const sceneSpan = Math.max(
    Number(sceneData.bounds_m.maximum[0]) - Number(sceneData.bounds_m.minimum[0]),
    Number(sceneData.bounds_m.maximum[1]) - Number(sceneData.bounds_m.minimum[1]),
  );
  uavGroup.scale.setScalar(THREE.MathUtils.clamp(sceneSpan / 350, 1, 2.8));
  contentRoot.add(uavGroup);
  state.layers.uav = uavGroup;
}

function setTrajectoryPoints(points) {
  if (!Array.isArray(points) || points.length < 2) return;
  removeTrajectory("baselineTrajectory");
  state.layers.trajectory = replaceTrajectory(
    "trajectory",
    points,
    new THREE.LineDashedMaterial({ color: 0x176a7d, dashSize: 12, gapSize: 7 }),
  );
  byId("route-comparison-panel").hidden = true;
  state.liveRoutes = null;
  applyLayerVisibility();
}

function removeTrajectory(layerName) {
  const route = state.layers[layerName];
  if (!route) return;
  contentRoot.remove(route);
  route.geometry.dispose();
  route.material.dispose();
  delete state.layers[layerName];
}

function replaceTrajectory(layerName, points, material, elevationOffset = 0) {
  removeTrajectory(layerName);
  const vertices = points.map((point) => {
    const vertex = canonicalPosition(point);
    vertex.y += elevationOffset;
    return vertex;
  });
  const route = new THREE.Line(new THREE.BufferGeometry().setFromPoints(vertices), material);
  route.computeLineDistances();
  route.renderOrder = 45;
  contentRoot.add(route);
  return route;
}

function metricText(value, unit, digits = 1) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)} ${unit}` : "—";
}

function signedMetric(value, unit, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const sign = number > 0 ? "+" : number < 0 ? "−" : "";
  return `${sign}${Math.abs(number).toFixed(digits)} ${unit}`;
}

function setLiveRouteComparison(routes) {
  const baseline = routes?.baseline;
  const connectivity = routes?.connectivity;
  if (!baseline?.points_m || !connectivity?.points_m) return false;
  state.liveRoutes = routes;
  state.layers.baselineTrajectory = replaceTrajectory(
    "baselineTrajectory",
    baseline.points_m,
    new THREE.LineDashedMaterial({ color: 0x5f686d, dashSize: 9, gapSize: 6, depthTest: false }),
    0.5,
  );
  state.layers.trajectory = replaceTrajectory(
    "trajectory",
    connectivity.points_m,
    new THREE.LineBasicMaterial({ color: 0x009688, depthTest: false }),
    0.9,
  );
  const base = baseline.metrics || {};
  const radio = connectivity.metrics || {};
  setText("route-threshold", `SINR ≥ ${Number(connectivity.planner_config?.minimum_sinr_db ?? 0).toFixed(1)} dB`);
  setText("route-base-length", metricText(base.length_m, "m"));
  setText("route-rf-length", metricText(radio.length_m, "m"));
  setText("route-base-min-sinr", metricText(base.minimum_sinr_db, "dB"));
  setText("route-rf-min-sinr", metricText(radio.minimum_sinr_db, "dB"));
  setText("route-base-mean-sinr", metricText(base.mean_sinr_db, "dB"));
  setText("route-rf-mean-sinr", metricText(radio.mean_sinr_db, "dB"));
  setText("route-base-outage", metricText(Number(base.outage_fraction) * 100, "%", 2));
  setText("route-rf-outage", metricText(Number(radio.outage_fraction) * 100, "%", 2));
  setText("route-base-handovers", Number(base.handover_count ?? 0));
  setText("route-rf-handovers", Number(radio.handover_count ?? 0));
  const baseLength = Number(base.length_m);
  const radioLength = Number(radio.length_m);
  const distanceCost = Number.isFinite(baseLength) && baseLength > 0 && Number.isFinite(radioLength)
    ? ((radioLength / baseLength) - 1) * 100
    : Number.NaN;
  const minimumSinrGain = Number(radio.minimum_sinr_db) - Number(base.minimum_sinr_db);
  const outageReduction = (Number(base.outage_fraction) - Number(radio.outage_fraction)) * 100;
  setText(
    "route-gain-summary",
    `可靠性变化：最低 SINR ${signedMetric(minimumSinrGain, "dB")} · 中断率下降 ${metricText(outageReduction, "百分点", 2)} · 距离代价 ${signedMetric(distanceCost, "%")}`,
  );
  byId("route-comparison-panel").hidden = false;
  applyLayerVisibility();
  return true;
}

function renderPreflight(result) {
  state.preflight = result;
  updateMissionButtons();
  const container = byId("preflight-results");
  container.replaceChildren();
  if (!result) {
    const message = document.createElement("p");
    message.textContent = state.configurationDirty
      ? "参数已修改，请重新生成后检查。"
      : "生成无线地图后可检查。";
    container.append(message);
    return;
  }
  const list = document.createElement("ul");
  list.className = "preflight-list";
  for (const check of result.checks || []) {
    const item = document.createElement("li");
    item.className = check.status === "pass" ? "is-pass" : "is-error";
    const body = document.createElement("span");
    body.textContent = check.label;
    const detail = document.createElement("small");
    detail.textContent = check.detail;
    body.append(detail);
    item.append(body);
    list.append(item);
  }
  container.append(list);
  if (result.guidance) {
    const guidance = document.createElement("p");
    guidance.className = "mission-guidance";
    guidance.textContent = result.guidance;
    container.append(guidance);
  }
}

async function runPreflight() {
  if (!state.runId || state.configurationDirty || !state.radio) return;
  const button = byId("run-preflight");
  button.disabled = true;
  setStatus("正在检查任务点、高度、指纹和通信可达性…");
  try {
    const response = await fetch("/api/preflight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: state.runId }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "运行前检查失败");
    renderPreflight(result);
    if (result.route?.points_m) setTrajectoryPoints(result.route.points_m);
    setStatus(result.status === "ready" ? "运行前检查通过，可以导入 LAESim" : "任务不可执行，请查看任务页诊断", result.status !== "ready");
  } catch (error) {
    renderPreflight({ checks: [{ label: "运行前检查", status: "error", detail: error.message }] });
    setStatus(error.message, true);
  } finally {
    button.disabled = state.configurationDirty || !state.radio;
  }
}

function radioScale(metric) {
  const fixed = metric === "sinr" ? [-10, 30] : [-125, -45];
  if (byId("radio-scale-mode").value === "fixed" || !state.radio) return fixed;
  const summary = state.radio.summary[metric];
  if (!Number.isFinite(summary?.p05) || !Number.isFinite(summary?.p95)) return fixed;
  const center = (summary.p05 + summary.p95) / 2;
  const span = Math.max(summary.p95 - summary.p05, metric === "sinr" ? 6 : 10);
  return [center - span / 2, center + span / 2];
}

function radioColor(value, limits) {
  const ratio = THREE.MathUtils.clamp((value - limits[0]) / (limits[1] - limits[0]), 0, 1);
  const scaled = ratio * (RADIO_COLORS.length - 1);
  const lower = Math.min(RADIO_COLORS.length - 2, Math.floor(scaled));
  return new THREE.Color(RADIO_COLORS[lower]).lerp(new THREE.Color(RADIO_COLORS[lower + 1]), scaled - lower);
}

function createRadioTexture(values, validMask, limits, nx, ny) {
  const image = document.createElement("canvas");
  image.width = nx;
  image.height = ny;
  const context = image.getContext("2d");
  context.imageSmoothingEnabled = false;
  for (let yi = 0; yi < ny; yi += 1) {
    for (let xi = 0; xi < nx; xi += 1) {
      const index = yi * nx + xi;
      if (!validMask[index]) {
        context.fillStyle = "#7b8387";
        context.fillRect(xi, ny - yi - 1, 1, 1);
        continue;
      }
      const color = radioColor(Number(values[index]), limits);
      context.fillStyle = `#${color.getHexString(THREE.SRGBColorSpace)}`;
      context.fillRect(xi, ny - yi - 1, 1, 1);
    }
  }
  const texture = new THREE.CanvasTexture(image);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

function addRadioLayer(radio) {
  const nx = radio.x_m.length;
  const ny = radio.y_m.length;
  if (!nx || !ny) return;
  const dx = nx > 1 ? Math.abs(radio.x_m[1] - radio.x_m[0]) : 20;
  const dy = ny > 1 ? Math.abs(radio.y_m[1] - radio.y_m[0]) : 20;
  const displayHeight = Number(radio.height_m) + 0.5;
  const geometry = new THREE.PlaneGeometry(dx * nx, dy * ny);
  geometry.rotateX(-Math.PI / 2);
  const metric = byId("radio-metric").value;
  const values = metric === "sinr" ? radio.serving_sinr_db : radio.best_rss_dbm;
  const texture = createRadioTexture(values, radio.finite_mask || radio.valid_mask, radioScale(metric), nx, ny);
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 1,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  });
  radioMesh = new THREE.Mesh(geometry, material);
  radioMesh.name = "radio";
  radioMesh.renderOrder = 20;
  radioMesh.position.set(
    (Number(radio.x_m[0]) + Number(radio.x_m[nx - 1])) / 2,
    displayHeight,
    -(Number(radio.y_m[0]) + Number(radio.y_m[ny - 1])) / 2,
  );
  contentRoot.add(radioMesh);
  state.layers.radio = radioMesh;
  updateRadioLegend();
}

function updateRadioLegend() {
  if (!state.radio) return;
  const metric = byId("radio-metric").value;
  const isSinr = metric === "sinr";
  const summary = state.radio.summary[metric];
  const unit = isSinr ? "dB" : "dBm";
  const limits = radioScale(metric);
  byId("radio-legend-label").textContent = isSinr ? "全频复用 SINR 信道地图" : "最强宽带 RSS 信道地图";
  byId("radio-map-height").textContent = `测量高度 ${Number(state.radio.height_m).toFixed(0)} m`;
  byId("radio-scale-min").textContent = `${limits[0].toFixed(1)} ${unit}`;
  byId("radio-scale-mid").textContent = `${((limits[0] + limits[1]) / 2).toFixed(1)} ${unit}`;
  byId("radio-scale-max").textContent = `${limits[1].toFixed(1)} ${unit}`;
  const statistics = Number.isFinite(summary?.median)
    ? `P5 ${summary.p05.toFixed(1)} · 中位数 ${summary.median.toFixed(1)} · P95 ${summary.p95.toFixed(1)} ${unit}`
    : "当前高度没有达到检测门限的网格";
  const coverage = `${(Number(state.radio.coverage.fraction) * 100).toFixed(1)}% 高于检测门限`;
  const integrity = `${(Number(state.radio.grid_integrity?.fraction ?? 0) * 100).toFixed(1)}% 网格有数值`;
  byId("radio-map-summary").textContent = `${statistics} · ${coverage} · ${integrity}`;
  const materialContract = state.radio.material_frequency_contract;
  const clampedMaterials = Object.entries(materialContract?.materials || {})
    .filter(([, value]) => value.clamped)
    .map(([name]) => name === "very_dry_ground" ? "干燥地面" : name === "concrete" ? "混凝土" : name);
  const materialNote = clampedMaterials.length
    ? ` · 材料边界代理：${clampedMaterials.join("、")}`
    : "";
  byId("radio-map-carrier").textContent = `${(Number(state.radio.frequency_hz) / 1e9).toFixed(1)} GHz · ${(Number(state.radio.bandwidth_hz) / 1e6).toFixed(0)} MHz · Sionna RT · ${Number(state.radio.cell_size_m).toFixed(0)} m 网格${materialNote}`;
}

function rebuildRadioLayer() {
  if (!state.radio || !radioMesh) return;
  contentRoot.remove(radioMesh);
  radioMesh.geometry.dispose();
  radioMesh.material.map?.dispose?.();
  radioMesh.material.dispose();
  addRadioLayer(state.radio);
  updateRadioLegend();
  applyLayerVisibility();
}

function currentUavPosition() {
  if (state.liveSync && state.livePosition) return state.livePosition;
  if (!state.sceneData?.tasks?.length) return null;
  const task = state.sceneData.tasks[0];
  const fraction = state.routeProgress / 100;
  return [
    THREE.MathUtils.lerp(Number(task.start_m[0]), Number(task.goal_m[0]), fraction),
    THREE.MathUtils.lerp(Number(task.start_m[1]), Number(task.goal_m[1]), fraction),
    numberValue("uav-altitude"),
  ];
}

function updateUavPosition(queryRadio = true) {
  const position = currentUavPosition();
  byId("route-progress-value").textContent = `${state.routeProgress.toFixed(0)}%`;
  if (!position || !uavGroup) return;
  uavGroup.position.copy(canonicalPosition(position));
  uavGroup.userData.selection.value.position_m = position;
  if (queryRadio) scheduleRadioQuery();
}

let radioQueryTimer = null;
function scheduleRadioQuery() {
  if (state.liveSync) return;
  if (!state.radio || !byId("radio-enabled").checked || !byId("uav-enabled").checked) {
    clearTimeout(radioQueryTimer);
    radioQueryTimer = null;
    byId("rf-panel").hidden = true;
    return;
  }
  if (state.radioQueryInFlight) {
    state.radioQueryPending = true;
    return;
  }
  const remainingMs = Math.max(0, 150 - (performance.now() - state.lastRadioQueryTime));
  clearTimeout(radioQueryTimer);
  if (remainingMs === 0) {
    radioQueryTimer = null;
    void queryRadioAtUav();
  } else {
    radioQueryTimer = setTimeout(() => {
      radioQueryTimer = null;
      void queryRadioAtUav();
    }, remainingMs);
  }
}

async function queryRadioAtUav() {
  if (state.liveSync) return;
  const position = currentUavPosition();
  if (!position || !state.runId) return;
  if (state.radioQueryInFlight) {
    state.radioQueryPending = true;
    return;
  }
  const queriedRunId = state.runId;
  state.radioQueryInFlight = true;
  state.lastRadioQueryTime = performance.now();
  try {
    const response = await fetch("/api/radio/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: queriedRunId, position_m: position }),
    });
    const observation = await response.json();
    if (!response.ok) throw new Error(observation.error || "无线查询失败");
    if (queriedRunId !== state.runId) return;
    displayRadioObservation(observation, position, "Sionna RT 离线地图");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    state.radioQueryInFlight = false;
    if (state.radioQueryPending) {
      state.radioQueryPending = false;
      scheduleRadioQuery();
    }
  }
}

function displayRadioObservation(observation, position, backend) {
  if (!observation || !position) return;
  const servingRss = observation.serving_cell ? observation.rss_dbm[observation.serving_cell] : null;
  byId("rf-position").textContent = position.map((value) => `${Number(value).toFixed(1)}`).join(", ") + " m";
  byId("rf-rsrp").textContent = servingRss == null ? "未检测到" : `${Number(servingRss).toFixed(1)} dBm`;
  byId("rf-sinr").textContent = observation.sinr_db == null ? "—" : `${Number(observation.sinr_db).toFixed(1)} dB`;
  byId("rf-cell").textContent = observation.serving_cell || "无";
  byId("rf-outage").textContent = observation.outage ? "中断" : "正常";
  byId("rf-outage").classList.toggle("is-outage", observation.outage);
  byId("rf-backend").textContent = backend;
  byId("rf-panel").hidden = false;
}

function setRadioLayerAvailability(available) {
  const toggle = document.querySelector('[data-layer="radio"]');
  const laesimToggle = byId("laesim-radio-visible");
  const visible = Boolean(available && state.radioLayerVisible);
  toggle.disabled = !available;
  toggle.checked = visible;
  laesimToggle.disabled = !available;
  laesimToggle.checked = visible;
  byId("radio-legend").hidden = !visible;
  if (!available) byId("rf-panel").hidden = true;
  applyLayerVisibility();
}

function setRadioLayerPreference(visible) {
  state.radioLayerVisible = Boolean(visible);
  const toggle = document.querySelector('[data-layer="radio"]');
  const laesimToggle = byId("laesim-radio-visible");
  toggle.checked = state.radioLayerVisible && !toggle.disabled;
  laesimToggle.checked = state.radioLayerVisible && !laesimToggle.disabled;
  applyLayerVisibility();
}

function syncFeatureControls() {
  const radioEnabled = byId("radio-enabled").checked;
  const uavEnabled = byId("uav-enabled").checked;
  byId("radio-controls").setAttribute("aria-disabled", String(!radioEnabled));
  byId("uav-controls").setAttribute("aria-disabled", String(!uavEnabled));
  byId("generate-label").textContent = radioEnabled ? "生成城市并计算无线" : "生成三维城市";
  document.querySelectorAll("#radio-controls input, #radio-controls select").forEach((control) => { control.disabled = !radioEnabled; });
  document.querySelectorAll("#uav-controls input, #uav-controls button").forEach((control) => { control.disabled = !uavEnabled; });
  const liveSync = byId("laesim-sync").checked;
  byId("route-progress").disabled = !uavEnabled || liveSync;
  byId("uav-altitude").disabled = true;
  byId("play-route").disabled = !uavEnabled || liveSync;
  if (state.layers.radio) state.layers.radio.visible = radioEnabled && document.querySelector('[data-layer="radio"]').checked;
  byId("radio-legend").hidden = !(
    state.radio && radioEnabled && document.querySelector('[data-layer="radio"]').checked
  );
  if (state.layers.uav) state.layers.uav.visible = uavEnabled && document.querySelector('[data-layer="uav"]').checked;
  const routeVisible = uavEnabled && document.querySelector('[data-layer="trajectory"]').checked;
  if (state.layers.trajectory) state.layers.trajectory.visible = routeVisible;
  if (state.layers.baselineTrajectory) state.layers.baselineTrajectory.visible = routeVisible;
  byId("route-comparison-panel").hidden = !uavEnabled || !state.liveRoutes;
  if (!radioEnabled || !uavEnabled) byId("rf-panel").hidden = true;
  else scheduleRadioQuery();
}

let laesimPollTimer = null;
let missionProcessPollTimer = null;

async function pollMissionProcess() {
  try {
    const response = await fetch("/api/laesim/mission-status", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "无法读取任务进程状态");
    updateMissionProcess(result);
  } catch (error) {
    setLaesimField("laesim-process-status", "状态读取失败", "is-error");
  } finally {
    clearTimeout(missionProcessPollTimer);
    missionProcessPollTimer = setTimeout(pollMissionProcess, 500);
  }
}

async function pollLaesimState() {
  if (!state.liveSync) return;
  try {
    const response = await fetch("/api/laesim/state", { cache: "no-store" });
    const live = await response.json();
    if (!response.ok) throw new Error(live.error || "无法读取 LAESim 状态");
    if (live.status === "idle") {
      byId("laesim-status").textContent = "等待 LAESim 任务启动…";
      setText("laesim-live-run", "尚无任务");
      setLaesimField("laesim-task-status", "等待任务");
      setText("laesim-planning-constraint", "—");
      setMissionGuidance();
      return;
    }
    const liveRunId = runIdFromPath(live.run_dir);
    setText("laesim-live-run", liveRunId || "未知");
    if (state.configurationDirty || (state.runId && liveRunId && liveRunId !== state.runId)) {
      const message = state.configurationDirty
        ? "网页参数已修改，请先重新生成，再启动对应任务。"
        : `检测到任务使用 ${liveRunId}，当前网页是 ${state.runId}；为避免混用数据，已拒绝同步。`;
      byId("laesim-status").textContent = "任务场景与当前网页不一致";
      setLaesimField("laesim-task-status", "场景不一致", "is-error");
      setMissionGuidance(message);
      return;
    }
    if (live.session_id !== state.liveSessionId) {
      const contextResponse = await fetch("/api/laesim/context", { cache: "no-store" });
      const context = await contextResponse.json();
      if (!contextResponse.ok) throw new Error(context.error || "无法加载 LAESim 场景");
      state.liveSessionId = live.session_id;
      state.liveRouteSessionId = null;
      state.livePosition = null;
      state.sceneData = context.scene;
      state.runId = context.run_id;
      state.radio = context.radio;
      byId("radio-enabled").checked = Boolean(context.radio);
      state.downloads = {};
      renderScene(context.scene, context.base_station_manifest);
      setRadioLayerAvailability(Boolean(context.radio));
      updateDownloads();
      updateLaesimRunStatus(context.laesim);
    }
    if (live.route && state.liveRouteSessionId !== live.session_id) {
      if (!setLiveRouteComparison(live.routes)) setTrajectoryPoints(live.route.points_m);
      state.liveRouteSessionId = live.session_id;
    }
    if (live.latest?.position_scene_m) {
      state.livePosition = live.latest.position_scene_m.map(Number);
      state.routeProgress = THREE.MathUtils.clamp(Number(live.progress || 0) * 100, 0, 100);
      setValue("route-progress", state.routeProgress);
      updateUavPosition(false);
    }
    if (live.radio && state.livePosition) {
      displayRadioObservation(live.radio, state.livePosition, "LAESim 位姿 + Sionna RT 离线地图");
    }
    const labels = { connecting: "正在连接 LAESim…", planning: "正在规划通信约束路线…", preview: "规划预览（尚未实飞）", flying: "LAESim 飞行同步中", complete: "LAESim 任务完成", stopped: "LAESim 任务已停止", error: `任务失败：${live.error || "未知错误"}` };
    byId("laesim-status").textContent = labels[live.status] || live.status;
    setLaesimField(
      "laesim-task-status",
      labels[live.status] || live.status,
      live.status === "error" ? "is-error" : (["flying", "complete"].includes(live.status) ? "is-ready" : ""),
    );
    const planning = live.planning || live.route?.planner_config || {};
    setText(
      "laesim-planning-constraint",
      Number.isFinite(Number(planning.minimum_sinr_db))
        ? `${Number(planning.flight_altitude_m ?? live.latest?.position_scene_m?.[2] ?? 0).toFixed(0)} m · SINR ≥ ${Number(planning.minimum_sinr_db).toFixed(1)} dB`
        : "等待规划",
    );
    setMissionGuidance(live.status === "error" ? liveErrorMessage(live) : "");
  } catch (error) {
    byId("laesim-status").textContent = error.message;
    setLaesimField("laesim-task-status", "读取失败", "is-error");
    setMissionGuidance(error.message);
  } finally {
    if (state.liveSync) laesimPollTimer = setTimeout(pollLaesimState, 250);
  }
}

function toggleLaesimSync() {
  state.liveSync = byId("laesim-sync").checked;
  state.routePlaying = false;
  clearTimeout(laesimPollTimer);
  laesimPollTimer = null;
  if (state.liveSync) {
    byId("laesim-status").textContent = "正在查找 LAESim 任务…";
    void pollLaesimState();
  } else {
    state.liveSessionId = null;
    state.liveRouteSessionId = null;
    state.livePosition = null;
    byId("laesim-status").textContent = "未连接，等待任务启动";
    setLaesimField("laesim-task-status", "同步关闭");
    setMissionGuidance();
    updateUavPosition();
  }
  syncFeatureControls();
}

function toggleRoutePlayback() {
  if (!byId("uav-enabled").checked || !state.sceneData) return;
  if (state.routeProgress >= 100) {
    state.routeProgress = 0;
    setValue("route-progress", 0);
    updateUavPosition();
  }
  state.routePlaying = !state.routePlaying;
  byId("play-route").innerHTML = state.routePlaying
    ? '<i data-lucide="pause"></i><span>暂停轨迹</span>'
    : '<i data-lucide="play"></i><span>播放轨迹</span>';
  if (window.lucide) window.lucide.createIcons({ attrs: { width: 16, height: 16 } });
}

function resetCamera(width, depth, maxHeight) {
  if (!state.sceneData) return;
  const sizeX = width ?? state.sceneData.bounds_m.maximum[0] - state.sceneData.bounds_m.minimum[0];
  const sizeY = depth ?? state.sceneData.bounds_m.maximum[1] - state.sceneData.bounds_m.minimum[1];
  const tallest = maxHeight ?? Math.max(...state.sceneData.buildings.map((item) => Number(item.size_m[2])), 1);
  const span = Math.max(sizeX, sizeY);
  camera.position.set(span * 0.78, Math.max(span * 0.62, tallest * 3), span * 0.78);
  controls.target.set(0, tallest * 0.18, 0);
  controls.minDistance = span * 0.08;
  controls.maxDistance = span * 3;
  camera.near = Math.max(0.1, span / 5000);
  camera.far = span * 6;
  camera.updateProjectionMatrix();
  controls.update();
  sunlight.shadow.camera.left = -span;
  sunlight.shadow.camera.right = span;
  sunlight.shadow.camera.top = span;
  sunlight.shadow.camera.bottom = -span;
  sunlight.shadow.camera.far = span * 4;
  sunlight.shadow.camera.updateProjectionMatrix();
}

function topCamera() {
  if (!state.sceneData) return;
  const width = state.sceneData.bounds_m.maximum[0] - state.sceneData.bounds_m.minimum[0];
  const depth = state.sceneData.bounds_m.maximum[1] - state.sceneData.bounds_m.minimum[1];
  const span = Math.max(width, depth);
  camera.position.set(0, span * 1.45, 0.01);
  controls.target.set(0, 0, 0);
  controls.update();
}

function applyLayerVisibility() {
  document.querySelectorAll("[data-layer]").forEach((input) => {
    const layer = input.dataset.layer;
    let visible = input.checked;
    if (layer === "radio") visible = visible && byId("radio-enabled").checked;
    if (["uav", "trajectory"].includes(layer)) visible = visible && byId("uav-enabled").checked;
    if (state.layers[layer]) state.layers[layer].visible = visible;
    if (layer === "trajectory" && state.layers.baselineTrajectory) {
      state.layers.baselineTrajectory.visible = visible;
    }
    if (layer === "radio") {
      byId("radio-legend").hidden = !visible;
      scheduleRadioQuery();
    }
  });
  const radioPrimaryView = Boolean(state.layers.radio?.visible);
  if (buildingMesh) {
    buildingMesh.material.transparent = radioPrimaryView;
    buildingMesh.material.opacity = radioPrimaryView ? 0.28 : 1;
    buildingMesh.material.depthWrite = !radioPrimaryView;
    buildingMesh.material.needsUpdate = true;
    buildingMesh.renderOrder = radioPrimaryView ? 30 : 0;
  }
}

function updateDownloads() {
  document.querySelectorAll(".download-action").forEach((button) => {
    button.disabled = !state.downloads[button.dataset.file];
  });
}

function downloadFile(filename) {
  const url = state.downloads[filename];
  if (!url) return;
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function selectionRows(type, value) {
  if (type === "建筑") return [
    ["编号", value.building_id], ["中心坐标", value.center_m.map((item) => `${Number(item).toFixed(1)} m`).join(", ")],
    ["尺寸", value.size_m.map((item) => `${Number(item).toFixed(1)} m`).join(" × ")], ["材料", value.material],
  ];
  if (type === "基站") return [
    ["站点", value.base_station_id], ["预设", `${value.preset_id ?? "custom"} · v${value.preset_version ?? "1.0.0"}`],
    ["部署", value.deployment_profile], ["功能", FUNCTION_TYPE_LABELS[value.metadata?.function_type] ?? value.metadata?.function_type ?? "—"],
    ["参数性质", PARAMETER_STATUS_LABELS[value.metadata?.parameter_status] ?? value.metadata?.parameter_status ?? "—"],
    ["通感能力", value.metadata?.sensing_enabled ? "预设启用（需独立感知模型）" : "未启用"],
    ["坐标", value.position_m.map((item) => `${Number(item).toFixed(1)} m`).join(", ")], ["功率", `${Number(value.nominal_tx_power_dbm).toFixed(1)} dBm/sector`],
    ["载波频率", `${(Number(value.carrier_frequency_hz) / 1e9).toFixed(1)} GHz`], ["信道带宽", `${(Number(value.bandwidth_hz) / 1e6).toFixed(0)} MHz`],
    ["扇区", String(value.sector_count)], ["方位", value.sectors.map((item) => `${Number(item.azimuth_deg)}°`).join(", ")],
  ];
  return [["任务", value.task_id], ["坐标", value.position_m.map((item) => `${Number(item).toFixed(1)} m`).join(", ")]];
}

function showSelection(type, value) {
  byId("selection-title").textContent = `${type} · ${value.building_id || value.base_station_id || value.task_id}`;
  const details = byId("selection-details");
  details.replaceChildren();
  for (const [label, content] of selectionRows(type, value)) {
    const dt = document.createElement("dt"); dt.textContent = label;
    const dd = document.createElement("dd"); dd.textContent = content;
    details.append(dt, dd);
  }
  byId("selection-panel").hidden = false;
}

function closeSelection() { byId("selection-panel").hidden = true; }

function beginTaskPointPick(kind) {
  byId("task-point-mode").value = "manual";
  syncTaskPointControls();
  state.taskPickMode = kind;
  canvas.classList.add("is-picking");
  byId("task-pick-guidance").hidden = false;
  byId("task-pick-guidance").textContent = `请在右侧城市地面点击${kind === "start" ? "起点" : "终点"}。`;
}

function cancelTaskPointPick() {
  state.taskPickMode = null;
  canvas.classList.remove("is-picking");
  byId("task-pick-guidance").hidden = true;
}

function pickTaskPointAtPointer(event) {
  if (!state.taskPickMode || !state.sceneData) return false;
  const bounds = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
  pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const world = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), world)) return true;
  contentRoot.updateMatrixWorld(true);
  const local = contentRoot.worldToLocal(world.clone());
  const x = THREE.MathUtils.clamp(local.x, 0, numberValue("size-x"));
  const y = THREE.MathUtils.clamp(-local.z, 0, numberValue("size-y"));
  const prefix = state.taskPickMode === "start" ? "task-start" : "task-goal";
  setValue(`${prefix}-x`, x.toFixed(1));
  setValue(`${prefix}-y`, y.toFixed(1));
  markConfigurationDirty();
  cancelTaskPointPick();
  setStatus(`${prefix === "task-start" ? "起点" : "终点"}已选择，请重新生成并运行检查`);
  return true;
}

function selectAtPointer(event) {
  if (pickTaskPointAtPointer(event)) return;
  const bounds = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
  pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(contentRoot.children, true);
  for (const hit of hits) {
    if (hit.object === buildingMesh && Number.isInteger(hit.instanceId)) {
      showSelection("建筑", buildingRecords[hit.instanceId]);
      return;
    }
    if (hit.object.userData.selection) {
      showSelection(hit.object.userData.selection.type, hit.object.userData.selection.value);
      return;
    }
  }
  closeSelection();
}

function resize() {
  const width = Math.max(1, viewport.clientWidth);
  const height = Math.max(1, viewport.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function animate() {
  const now = performance.now();
  const elapsed = Math.min(0.1, (now - state.lastFrameTime) / 1000);
  state.lastFrameTime = now;
  if (state.routePlaying) {
    const next = state.routeProgress + elapsed * 5;
    state.routeProgress = Math.min(100, next);
    setValue("route-progress", state.routeProgress);
    updateUavPosition();
    if (next >= 100) toggleRoutePlayback();
  }
  controls.update();
  renderer.render(scene3d, camera);
  requestAnimationFrame(animate);
}

async function initialize() {
  setupTabs();
  if (window.lucide) window.lucide.createIcons({ attrs: { width: 16, height: 16 } });
  void pollMissionProcess();
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error("无法读取预设参数");
    state.presets = await response.json();
    const installed = Boolean(state.presets.capabilities?.sionna_rt_installed);
    byId("sionna-status").textContent = installed
      ? "运行环境已安装；开启后才执行计算"
      : "当前启动环境缺少 Sionna RT，请重新运行启动器";
    byId("radio-enabled").disabled = !installed;
    populatePresets(state.presets);
    syncTaskPointControls();
    syncFeatureControls();
    const liveResponse = await fetch("/api/laesim/state", { cache: "no-store" });
    const live = liveResponse.ok ? await liveResponse.json() : { status: "idle" };
    if (live.status !== "idle" && live.session_id) {
      byId("laesim-sync").checked = true;
      toggleLaesimSync();
    } else {
      await generateCity({ includeRadio: false });
    }
  } catch (error) {
    setStatus(error.message, true);
  }
}

byId("city-preset").addEventListener("change", async (event) => {
  applyCityPreset(event.target.value);
  if (event.target.value !== "custom") await generateCity({ includeRadio: false });
});
byId("station-preset").addEventListener("change", (event) => applyStationPreset(event.target.value));
byId("mission-preset").addEventListener("change", (event) => applyMissionPreset(event.target.value));
document.querySelectorAll("#mission-constraint-controls input").forEach((input) => input.addEventListener("input", () => {
  byId("mission-preset").value = "custom";
  applyMissionPreset("custom");
}));
byId("task-point-mode").addEventListener("change", syncTaskPointControls);
byId("pick-task-start").addEventListener("click", () => beginTaskPointPick("start"));
byId("pick-task-goal").addEventListener("click", () => beginTaskPointPick("goal"));
byId("city-panel").addEventListener("input", (event) => {
  if (!["city-preset", "seed"].includes(event.target.id)) byId("city-preset").value = "custom";
});
byId("station-panel").addEventListener("input", (event) => {
  if (event.target.id !== "station-preset") {
    byId("station-preset").value = "custom";
    applyStationPreset("custom");
  }
  syncCarrierSummary();
});
byId("generator-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const includeRadio = byId("radio-enabled").checked;
  void generateCity({ includeRadio });
});
byId("reset-camera").addEventListener("click", () => resetCamera());
byId("top-camera").addEventListener("click", topCamera);
byId("close-selection").addEventListener("click", closeSelection);
canvas.addEventListener("click", selectAtPointer);
document.querySelectorAll("[data-layer]").forEach((input) => input.addEventListener("change", () => {
  if (input.dataset.layer === "radio") setRadioLayerPreference(input.checked);
  else applyLayerVisibility();
}));
byId("radio-enabled").addEventListener("change", syncFeatureControls);
byId("uav-enabled").addEventListener("change", syncFeatureControls);
byId("laesim-sync").addEventListener("change", toggleLaesimSync);
byId("laesim-radio-visible").addEventListener("change", (event) => setRadioLayerPreference(event.target.checked));
byId("route-progress").addEventListener("input", () => {
  state.routeProgress = numberValue("route-progress");
  updateUavPosition();
});
byId("task-altitude").addEventListener("input", () => setValue("uav-altitude", numberValue("task-altitude")));
byId("uav-altitude").addEventListener("change", () => {
  if (state.sceneData) {
    const task = state.sceneData.tasks[0];
    const altitude = numberValue("uav-altitude");
    const points = [task.start_m, task.goal_m].map((point) => [point[0], point[1], altitude]);
    setTrajectoryPoints(points);
    updateUavPosition();
  }
});
byId("play-route").addEventListener("click", toggleRoutePlayback);
byId("run-preflight").addEventListener("click", () => void runPreflight());
byId("import-laesim").addEventListener("click", () => void runLaesimAction("/api/laesim/import"));
byId("open-laesim").addEventListener("click", () => void runLaesimAction("/api/laesim/open"));
byId("start-laesim-mission").addEventListener("click", () => void runMissionProcessAction("start"));
byId("stop-laesim-mission").addEventListener("click", () => void runMissionProcessAction("stop"));
byId("radio-metric").addEventListener("change", rebuildRadioLayer);
byId("radio-scale-mode").addEventListener("change", rebuildRadioLayer);
document.querySelectorAll(".download-action").forEach((button) => button.addEventListener("click", () => downloadFile(button.dataset.file)));
byId("generator-form").addEventListener("input", (event) => {
  const localOnly = new Set(["laesim-sync", "laesim-radio-visible", "uav-enabled", "route-progress", "radio-metric", "radio-scale-mode"]);
  if (!localOnly.has(event.target.id)) markConfigurationDirty();
});
new ResizeObserver(resize).observe(viewport);
resize();
animate();
initialize();
