const LabModel = {
  createNote(notes, text) {
    if (typeof text !== "string" || Array.from(text).length < 1 || Array.from(text).length > 160) {
      return { status: 400, error: "Текст должен содержать от 1 до 160 символов." };
    }
    if (new TextEncoder().encode(JSON.stringify({ text })).length > 4096) {
      return { status: 413, error: "Тело запроса превышает 4096 байт." };
    }
    if (notes.length >= 100) {
      return { status: 409, error: "В хранилище уже 100 заметок. Очистите этот список для нового опыта." };
    }
    const note = { id: notes.length + 1, text };
    return { status: 201, note, notes: [...notes, note] };
  },
  experiment(platform, profile, operation, snapshots) {
    const state = snapshots[platform][profile];
    if (operation === "rootfs") {
      return state.rootfs_write.allowed
        ? "Запись в /etc разрешена. Корневая файловая система доступна для записи."
        : "Запись в /etc отклонена: Read-only file system. Корневая файловая система доступна только для чтения.";
    }
    if (operation === "data") {
      return state.data_write.allowed
        ? "Запись в /data разрешена. Рабочие данные находятся в отдельном томе."
        : "Запись в /data отклонена.";
    }
    if (operation === "token") {
      return "HTTP 401. Хранилище требует внутренний токен и отклоняет запрос без него.";
    }
    if (platform !== "kubernetes") {
      return "Этот опыт относится к Kubernetes.";
    }
    if (operation === "outsider") {
      return profile === "baseline"
        ? "HTTP 200. Посторонний Pod достигает /health хранилища. Ограничивающей NetworkPolicy нет."
        : "Тайм-аут. NetworkPolicy блокирует прямое соединение outsider → store; reader → gateway → store разрешено.";
    }
    if (operation === "admission") {
      return profile === "hardened"
        ? "Forbidden. Сервер отклоняет привилегированный root Pod до запуска: нарушение уровня Restricted."
        : "Обычный namespace использует уровень Privileged. Отдельный опыт с таким Pod в обычном варианте не записан в протоколе.";
    }
    return "Неизвестное действие.";
  }
};
