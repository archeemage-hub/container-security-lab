const names = {
  "Process identity": "Пользователь процесса",
  "Root filesystem write": "Запись в корневую файловую систему",
  "Application data write": "Запись данных приложения",
  "Temporary directory write": "Запись временных файлов",
  "Seccomp filtering active": "Фильтрация seccomp",
  "No Docker socket in application": "Отсутствие Docker socket",
  "Create and read a note": "Создание и чтение заметки",
  "Backend authentication": "Проверка токена хранилищем",
  "Capabilities removed": "Удаление Linux capabilities",
  "Privilege escalation blocked": "Запрет повышения привилегий",
  "Runtime token absent from image filesystem": "Отсутствие токена в файловой системе образа",
  "Writable data and temporary volumes": "Запись в рабочие и временные тома",
  "ServiceAccount token mount": "Подключение токена ServiceAccount",
  "Unrelated Pod to backend": "Доступ постороннего Pod к хранилищу",
  "Allowed reader to gateway to backend": "Разрешённая цепочка reader → gateway → store",
  "RBAC notes-app lists secrets": "Права приложения на список Secrets",
  "RBAC notes-app lists pods": "Права приложения на список Pod",
  "RBAC notes-observer lists secrets": "Права наблюдателя на список Secrets",
  "RBAC notes-observer lists pods": "Права наблюдателя на список Pod",
  "Privileged root Pod rejected before launch": "Отклонение привилегированного Pod",
  "Secret encrypted in cluster datastore": "Шифрование Secret в базе кластера",
  "Structured logs contain no runtime token": "Отсутствие токена в журналах"
};

const environments = {
  "Docker baseline": "Docker · обычный",
  "Docker hardened": "Docker · усиленный",
  "Kubernetes baseline": "Kubernetes · обычный",
  "Kubernetes hardened": "Kubernetes · усиленный",
  Image: "Образ приложения",
  Logging: "Журналы"
};

let platform = "kubernetes";
let profile = "hardened";
let notes = [];
let persistent = true;
const memory = new Map();
const find = id => document.getElementById(id);
const key = () => `container-security-lab-demo-v1/${platform}/${profile}`;

function cell(row, text) {
  const element = document.createElement("td");
  element.textContent = text;
  row.append(element);
  return element;
}

function loadNotes() {
  let value = memory.get(key()) || [];
  try {
    const raw = localStorage.getItem(key());
    if (raw !== null) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length <= 100 && parsed.every((note, i) =>
          note && note.id === i + 1 && typeof note.text === "string" &&
          Array.from(note.text).length > 0 && Array.from(note.text).length <= 160)) {
        value = parsed;
      }
    }
  } catch {
    persistent = false;
  }
  notes = value;
  find("storage-status").textContent = persistent
    ? "Заметки сохраняются в этом браузере отдельно для каждой конфигурации."
    : "Хранилище браузера недоступно. Заметки останутся только до закрытия страницы.";
}

function saveNotes() {
  memory.set(key(), notes);
  try {
    localStorage.setItem(key(), JSON.stringify(notes));
  } catch {
    persistent = false;
    find("storage-status").textContent = "Хранилище браузера недоступно. Заметки останутся только до закрытия страницы.";
  }
}

function renderNotes() {
  const list = find("note-list");
  list.replaceChildren();
  find("note-caption").textContent = `Заметки: ${notes.length} / 100`;
  if (notes.length === 0) {
    const row = document.createElement("tr");
    cell(row, "—");
    cell(row, "Заметок пока нет. Создайте первую.");
    list.append(row);
  }
  for (const note of notes) {
    const row = document.createElement("tr");
    cell(row, note.id);
    cell(row, note.text);
    list.append(row);
  }
}

function renderConfiguration() {
  const label = `${platform === "docker" ? "Docker" : "Kubernetes"} · ${profile === "hardened" ? "усиленный" : "обычный"} вариант`;
  find("configuration-description").textContent = `${label}. Код приложения одинаковый; меняются настройки запуска.`;
  const state = labEvidence.snapshots[platform][profile];
  const parameters = [
    ["UID / GID", `${state.uid} / ${state.gid}`],
    ["Запись в /etc", state.rootfs_write.allowed ? "Разрешена" : "Отклонена"],
    ["Запись в /data и /tmp", state.data_write.allowed && state.temporary_write.allowed ? "Разрешена" : "Ограничена"],
    ["CapEff", state.cap_eff],
    ["NoNewPrivs", state.no_new_privs],
    ["Seccomp", `${state.seccomp}${state.seccomp === "2" ? " · фильтрация включена" : " · фильтрация не включена"}`],
    ["Токен ServiceAccount", state.service_account_token ? "Подключён" : "Отсутствует"],
    ["Docker socket", state.docker_socket ? "Подключён" : "Отсутствует"]
  ];
  const body = find("process-state");
  body.replaceChildren();
  for (const [name, value] of parameters) {
    const row = document.createElement("tr");
    cell(row, name);
    cell(row, value);
    body.append(row);
  }
  for (const button of document.querySelectorAll("[data-operation]")) {
    button.disabled = platform === "docker" && ["outsider", "admission"].includes(button.dataset.operation);
  }
  find("experiment-status").textContent = "Результат выбранного действия появится здесь.";
  loadNotes();
  renderNotes();
  find("note-status").textContent = `HTTP 200 · прочитан список для конфигурации «${label}».`;
}

function renderEvidence() {
  const filter = find("evidence-filter").value;
  const checks = labEvidence.results.checks.filter(check => filter === "all" || check.environment === filter);
  const body = find("check-list");
  body.replaceChildren();
  for (const check of checks) {
    const row = document.createElement("tr");
    cell(row, check.id);
    cell(row, environments[check.environment] || check.environment);
    const description = cell(row, names[check.name] || check.name);
    const detail = document.createElement("details");
    detail.className = "check-detail";
    const summary = document.createElement("summary");
    summary.textContent = "Ожидание и факт";
    const values = document.createElement("pre");
    values.textContent = JSON.stringify({ expected: check.expected, actual: check.actual }, null, 2);
    detail.append(summary, values);
    description.append(detail);
    const status = cell(row, check.passed ? "Пройдена" : "Не пройдена");
    status.className = check.passed ? "passed" : "failed";
    body.append(row);
  }
  find("evidence-count").textContent = `Показано ${checks.length} из ${labEvidence.results.total} проверок.`;
}

find("note-form").addEventListener("submit", event => {
  event.preventDefault();
  loadNotes();
  const result = LabModel.createNote(notes, find("note-text").value);
  if (result.status !== 201) {
    find("note-status").textContent = `HTTP ${result.status} · ${result.error}`;
    return;
  }
  notes = result.notes;
  saveNotes();
  renderNotes();
  find("note-text").value = "";
  find("note-counter").textContent = "0 / 160 символов";
  find("note-status").textContent = `HTTP 201 · заметка № ${result.note.id} создана.`;
});

find("note-text").addEventListener("input", event => {
  const count = Array.from(event.target.value).length;
  find("note-counter").textContent = `${count} / 160 символов`;
  find("note-counter").className = count > 160 ? "failed" : "";
});

find("read-notes").addEventListener("click", () => {
  loadNotes();
  renderNotes();
  find("note-status").textContent = `HTTP 200 · прочитан список из ${notes.length} заметок.`;
});

find("clear-notes").addEventListener("click", () => {
  notes = [];
  saveNotes();
  renderNotes();
  find("note-status").textContent = "Список выбранной конфигурации очищен в этом браузере.";
});

for (const input of document.querySelectorAll('input[name="platform"], input[name="profile"]')) {
  input.addEventListener("change", () => {
    platform = document.querySelector('input[name="platform"]:checked').value;
    profile = document.querySelector('input[name="profile"]:checked').value;
    renderConfiguration();
  });
}

for (const button of document.querySelectorAll("[data-operation]")) {
  button.addEventListener("click", () => {
    find("experiment-status").textContent = "Модель: " + LabModel.experiment(platform, profile, button.dataset.operation, labEvidence.snapshots);
  });
}

find("evidence-filter").addEventListener("change", renderEvidence);
window.addEventListener("storage", event => {
  if (event.key === key() || event.key === null) {
    loadNotes();
    renderNotes();
  }
});

const passed = labEvidence.results.checks.filter(check => check.passed).length;
const measured = new Date(labEvidence.environment.timestamp_utc).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" });
find("evidence-summary").textContent = `Пройдено ${passed} из ${labEvidence.results.total} проверок. Измерение: ${measured} по Москве.`;
find("environment-description").textContent = `Linux ${labEvidence.environment.kernel}; Docker ${labEvidence.environment.docker}; K3s ${labEvidence.environment.kubernetes}.`;
if (siteConfig.repository) {
  find("source-link").href = siteConfig.repository;
  find("source-link").hidden = false;
  find("guide-link").href = siteConfig.repository + "/blob/main/docs/GUIDE.md";
}
renderConfiguration();
renderEvidence();
