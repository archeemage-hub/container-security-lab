# Запуск и проверка Container Security Lab

Container Security Lab - воспроизводимый стенд для сравнения обычных
и усиленных конфигураций Docker и Kubernetes. Приложение состоит из шлюза
и хранилища заметок. Один образ запускается с разными ограничениями;
результаты функциональных и защитных проверок записываются в `evidence/`.

[Исходники](https://github.com/archeemage-hub/container-security-lab) |
[Версия 1.0.2](https://github.com/archeemage-hub/container-security-lab/tree/v1.0.2) |
[Браузерная демонстрация](https://archeemage-hub.github.io/container-security-lab/)

## Требования

- Linux x86_64.
- Docker Engine с работающим доступом к daemon и плагином Docker Compose.
- Python 3.10 или новее; дополнительные Python-пакеты не нужны.
- 3 ГиБ памяти и 2 CPU для контейнера K3s, дополнительно ресурсы для системы
  и контейнеров приложения.
- Свободные локальные порты 18080, 18081 и 16443.
- Доступ к Интернету для первой загрузки базового и служебных образов.

Kubernetes, containerd и kubectl входят в образ K3s. Установка отдельного
кластера и изменение пользовательского kubeconfig не требуются.

Проверка доступности инструментов:

```bash
docker version
docker compose version
python3 --version
```

В выводе `docker version` должны присутствовать Client и Server.

## Получение исходников

```bash
git clone --branch v1.0.2 https://github.com/archeemage-hub/container-security-lab.git
cd container-security-lab
```

Тег фиксирует версию, используемую для воспроизведения результатов статьи.
Для работы с текущей веткой используйте `git clone` без `--branch`.
При загрузке ZIP через GitHub сначала распакуйте архив и откройте терминал
в его корне. Команды ниже выполняются из папки с `Dockerfile` и `scripts/`.

## Развёртывание

Загрузить закреплённый базовый образ:

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
```

Собрать приложение и запустить весь стенд:

```bash
python3 scripts/deploy.py
```

Скрипт создаёт токен в `.runtime/`, собирает образ `container-security-lab:1.0`,
запускает два проекта Compose и узел `csl-k3s`. Затем импортирует образ
в containerd, применяет манифесты, создаёт Secrets и ожидает готовности Pod.
Первый запуск загружает отсутствующие образы и может занять несколько минут.

Признак завершения:

```text
Both profiles are ready. Run scripts/verify.py to reproduce the checks.
```

| Объекты | Назначение |
|---|---|
| Compose `csl-baseline` | Обычная конфигурация приложения |
| Compose `csl-hardened` | Усиленная конфигурация приложения |
| Compose `csl-cluster`, контейнер `csl-k3s` | Локальный узел Kubernetes |
| Namespace `article-baseline` | Обычная конфигурация Kubernetes |
| Namespace `article-secure` | Усиленная конфигурация Kubernetes |

Состояние развёртывания:

```bash
docker compose -p csl-baseline -f compose.baseline.yaml ps
docker compose -p csl-hardened -f compose.hardened.yaml ps
docker exec csl-k3s /bin/kubectl get pods -n article-baseline
docker exec csl-k3s /bin/kubectl get pods -n article-secure
```

В каждом Compose-проекте `gateway` и `store` должны иметь статус healthy.
В каждом namespace ожидаются готовые Pod шлюза, хранилища, `reader` и `outsider`.

## Работа приложения

```text
Клиент → gateway → store → /data/notes.json
```

`APP_ROLE` выбирает роль Python-приложения. Шлюз принимает HTTP-запросы
и передаёт их в store с внутренним токеном. Хранилище проверяет токен,
читает заметки из JSON и выполняет атомарную запись через временный файл.
Доступ к данным в процессе защищён блокировкой.

| Вариант Docker | Адрес шлюза |
|---|---|
| Обычный | `http://127.0.0.1:18081/notes` |
| Усиленный | `http://127.0.0.1:18080/notes` |

GET `/notes` возвращает `notes` и `count`. POST `/notes` принимает
JSON-объект с полем `text`. Пределы: 1-160 символов, 100 заметок
в хранилище и 4096 байт на тело запроса.

```bash
curl -i -H 'Content-Type: application/json' -d '{"text":"Проверка сервиса"}' http://127.0.0.1:18080/notes
curl http://127.0.0.1:18080/notes
```

Ожидаются HTTP 201 при создании и HTTP 200 при чтении. Для обычного варианта
используется порт 18081. Без curl последовательность можно проверить через
диагностический модуль:

```bash
docker exec csl-hardened-gateway-1 python /app/probe.py --notes http://127.0.0.1:8080/notes
```

Токен хранится вне исходников и подключается файлом только к шлюзу
и хранилищу. `.runtime/` исключена из Git и контекста сборки.

## Автоматическая проверка

```bash
python3 scripts/verify.py
```

Ожидаемый итог:

```text
Passed 41 of 41 checks.
```

Сценарий проверяет UID, права записи, capabilities, NoNewPrivs, seccomp,
работу приложения, сетевую изоляцию, RBAC, Pod Security Admission,
шифрование Secret, отсутствие токена в файловой системе образа и журналах.
Запрет операции считается успешным результатом, если он соответствует
ожидаемому условию. Функциональная проверка сверяет HTTP-коды, наличие
созданной заметки и увеличение числа записей.

Каждый запуск добавляет по одной заметке в проверяемые конфигурации
и обновляет `evidence/`. Для проверки шифрования скрипт кратко приостанавливает
`csl-k3s`, копирует SQLite/Kine в `.runtime/` и возобновляет контейнер.

| Файл в `evidence/` | Содержание |
|---|---|
| `checks.json` | Все условия, ожидаемые и фактические значения, итог |
| `runtime-snapshots.json` | Параметры процессов и результаты проб записи |
| `environment.json` | Время измерения, версии среды, идентификаторы образов |
| `admission-rejection.txt` | Отказ Restricted при серверном dry-run |
| `encryption-status.txt` | Статус шифрования K3s |
| `application-logs.jsonl` | События HTTP-запросов |
| `ARTICLE_MAP.md` | Соответствие утверждений статьи материалам проекта |

В записанном протоколе `passed` и `total` равны 41. После аварийного завершения
сценария файл может остаться от предыдущего запуска; подтверждением нового
запуска служит новое итоговое сообщение и время в `environment.json`.

## Ручные проверки ограничений

### Процесс и файловая система

```bash
docker exec csl-baseline-store-1 python /app/probe.py
docker exec csl-hardened-store-1 python /app/probe.py
docker exec csl-k3s /bin/kubectl exec -n article-secure deployment/store -- python /app/probe.py
```

| Поле | Обычный вариант | Усиленный вариант |
|---|---|---|
| `uid` | 0 | 10001 |
| `rootfs_write.allowed` | true | false |
| `data_write.allowed`, `temporary_write.allowed` | true | true |
| `cap_eff` | Ненулевой набор | Ноль |
| `no_new_privs` | `"0"` | `"1"` |
| `service_account_token` в Kubernetes | true | false |
| `docker_socket` | false | false |

Seccomp равен `"2"` в обоих Docker-вариантах и в усиленном Kubernetes.
Модуль создаёт собственные пробные файлы и удаляет их после проверки.

### Сетевая изоляция Kubernetes

Разрешённый клиент:

```bash
docker exec csl-k3s /bin/kubectl exec -n article-secure reader -- python /app/probe.py http://gateway:8080/notes
```

Ожидаются `reachable: true` и HTTP 200. Проверка постороннего Pod:

```bash
lab_store_ip="$(docker exec csl-k3s /bin/kubectl get pod -n article-secure -l app=store -o jsonpath='{.items[0].status.podIP}')"
docker exec csl-k3s /bin/kubectl exec -n article-secure outsider -- python /app/probe.py "http://${lab_store_ip}:8080/health"
```

Ожидается тайм-аут. При замене `article-secure` на `article-baseline`
в обеих строках ожидается HTTP 200. IP хранилища нужно получать отдельно
для каждого namespace. Доступ к `/health` по IP исключает зависимость
результата от DNS и токена хранилища.

### RBAC и шифрование

```bash
docker exec csl-k3s /bin/kubectl auth can-i list pods -n article-secure --as=system:serviceaccount:article-secure:notes-observer
docker exec csl-k3s /bin/kubectl auth can-i list secrets -n article-secure --as=system:serviceaccount:article-secure:notes-observer
docker exec csl-k3s /bin/k3s secrets-encrypt status
```

Ожидаются `yes`, `no` и включённое шифрование. У запрета `no` возможен
ненулевой код завершения. Проверка содержимого базы, включая префикс
зашифрованной записи и отсутствие открытого токена, выполняется `verify.py`.

## Браузерная демонстрация

Статическая страница находится в `docs/index.html` и размещается на
GitHub Pages. Она позволяет создавать заметки в localStorage, переключать
конфигурации, выполнять модельные опыты и просматривать сохранённый протокол.
Результаты настоящего контейнерного стенда отделены от состояния демонстрации.

Страницу можно открыть как локальный HTML вместе с остальными файлами `docs`
либо через HTTP:

```bash
python3 -m http.server 8088 --directory docs --bind 127.0.0.1
```

Адрес просмотра - `http://127.0.0.1:8088/`; остановка сервера - Ctrl+C.
Для страницы не требуется Docker. GitHub Pages публикует статические файлы
и не выполняет Python-приложение или кластер Kubernetes.

После новых измерений обновляются данные страницы и контрольные суммы:

```bash
python3 scripts/build_demo.py
python3 scripts/update_manifest.py
sha256sum -c MANIFEST.sha256
```

`build_demo.py` берёт результаты из `evidence/`; ручное изменение результатов
в `docs/data.js` не требуется. Параметры публикации Pages: ветка `main`,
папка `/docs`. `.nojekyll` отключает генерацию сайта через Jekyll.

## Остановка и сброс

Остановка с сохранением томов:

```bash
docker compose -p csl-baseline -f compose.baseline.yaml stop
docker compose -p csl-hardened -f compose.hardened.yaml stop
docker compose -p csl-cluster -f compose.cluster.yaml stop
```

Повторное развёртывание выполняется через `scripts/deploy.py`. Для полного
сброса учебных заметок и состояния этого кластера:

```bash
docker compose -p csl-baseline -f compose.baseline.yaml down -v
docker compose -p csl-hardened -f compose.hardened.yaml down -v
docker compose -p csl-cluster -f compose.cluster.yaml down -v
```

Глобальная очистка Docker не требуется.

## Диагностика

| Ситуация | Проверка |
|---|---|
| Docker Server недоступен | Состояние daemon и доступ текущего пользователя |
| Порт занят | `ss -ltnp` для портов 18080, 18081 и 16443 |
| Узел K3s не стал Ready | Свободная память и `docker logs --tail 100 csl-k3s` |
| Pod не готов, `ImagePullBackOff` | `kubectl describe`; повторный импорт образа через `deploy.py` |
| HTTP 503 от шлюза | Готовность store, файл токена и журналы приложения |
| HTTP 400 при создании | JSON и строка `text` длиной 1-160 символов |
| HTTP 413 | Тело запроса не более 4096 байт |
| HTTP 409 | Достигнут предел 100 заметок |
| FAIL в проверках | Поля `actual` и `expected` в протоколе |

```bash
docker logs --tail 50 csl-hardened-gateway-1
docker logs --tail 50 csl-hardened-store-1
docker exec csl-k3s /bin/kubectl get events -n article-secure --sort-by=.metadata.creationTimestamp
docker exec csl-k3s /bin/kubectl describe deployment store -n article-secure
docker exec csl-k3s /bin/kubectl logs -n article-secure deployment/store --tail=50
```

После устранения ошибки следует повторить развёртывание и проверку.

## Область применения

Стенд предназначен для исследования конкретных механизмов изоляции.
В шлюзе не реализованы TLS и пользовательская аутентификация.
Данные Docker сохраняются в именованных томах; `emptyDir` в Kubernetes
теряет данные при замене Pod. Узел K3s внутри Docker требует privileged,
усиленные контейнеры приложения его не используют.

41/41 не является процентной оценкой безопасности. Поиск CVE, атаки на ядро,
нагрузочные испытания и промышленная отказоустойчивость не исследовались.
Ссылка на версию проекта и соответствие протокола выводам статьи приведены
в `evidence/ARTICLE_MAP.md`.
