# Гайд по проекту и публикации на GitHub

Этот гайд объясняет устройство Container Security Lab, запуск Docker и Kubernetes,
проверку результатов и публикацию исходников на GitHub. Начните с разделов 1–3,
затем выполните публикацию по разделу 6. Для статьи сохраните отдельную версию
`v1.0.0` и укажите ссылку на неё в библиографическом источнике № 1.

Команды рассчитаны на Linux и выполняются из корня проекта, где находятся
`Dockerfile`, `README.md` и папки `app`, `k8s`, `scripts`. Строки `ВАШ_ЛОГИН`,
`ВАШЕ ИМЯ` и `ВАШ_EMAIL` замените своими данными до выполнения команды.
Проект опубликован в [репозитории GitHub](https://github.com/archeemage-hub/container-security-lab).
[HTML-демонстрация](https://archeemage-hub.github.io/container-security-lab/) работает
в браузере. Раздел 6 описывает первую публикацию в новый пустой репозиторий;
для работы с опубликованным проектом удобнее получить его командой `git clone`.

## 1 Подготовка

Получить исходники из GitHub можно следующими командами:

```bash
git clone https://github.com/archeemage-hub/container-security-lab.git
cd container-security-lab
```

Если используете выданный архив, распакуйте `container-security-lab.zip`. Откройте получившуюся папку
`container-security-lab` в файловом менеджере и выберите «Открыть в терминале».
Не открывайте терминал в папке, которая содержит только ZIP-архив.

Проверьте, что вы находитесь в нужной папке:

```bash
pwd
ls -a
```

Для запуска нужны Docker Engine, плагин Docker Compose, Python 3.10 или новее
и Linux x86_64. Узлу K3s выделяется 3 ГиБ памяти и 2 CPU; дополнительно нужна
память для системы и контейнеров приложения. При первом запуске потребуется
Интернет и свободное место для образов. Отдельный Kubernetes и kubectl
на компьютер устанавливать не нужно: они находятся в контейнере `csl-k3s`.

```bash
docker version
docker compose version
python3 --version
```

В `docker version` должны отображаться разделы Client и Server. Если Server
недоступен, сначала запустите Docker и настройте доступ к нему. Пакеты
для Python устанавливать не требуется: приложение использует стандартную библиотеку.

## 2 Запуск и автоматическая проверка

Сначала загрузите закреплённый базовый образ. Если он уже есть, повторная
команда проверит его наличие и не создаст вторую копию:

```bash
docker pull python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
```

Запустите стенд:

```bash
python3 scripts/deploy.py
```

Скрипт создаёт локальный токен в `.runtime/`, собирает образ приложения,
запускает два варианта Docker Compose и отдельный узел K3s. Затем он
импортирует тот же образ в Kubernetes, применяет манифесты, создаёт Secrets
и ждёт готовности приложений и диагностических Pod. Образ K3s и его служебные
образы загружаются при необходимости. Первое развёртывание может занять
несколько минут. Дождитесь сообщения:

```text
Both profiles are ready. Run scripts/verify.py to reproduce the checks.
```

Теперь выполните проверку:

```bash
python3 scripts/verify.py
```

Ожидаемый итог:

```text
Passed 41 of 41 checks.
```

`PASS` означает, что ожидаемое условие подтвердилось. Запрещённая операция
тоже даёт `PASS`, если защита действительно её заблокировала. Например,
отказ записи в `/etc` в усиленном варианте — успешный результат проверки.
`FAIL` или остановка с ошибкой требуют разбора по разделу 8.

Проверка создаёт по одной заметке в каждом варианте и обновляет файлы
`evidence/`. Перед проверкой шифрования скрипт кратко приостанавливает
только `csl-k3s`, копирует SQLite/Kine в приватную папку `.runtime/` и
возобновляет контейнер. Параллельно эту часть стенда лучше не изменять.

## 3 Как устроен проект

Один Python-файл `app/app.py` выполняет две роли. При `APP_ROLE=gateway`
он принимает запросы клиента и передаёт их в хранилище. При `APP_ROLE=store`
он читает и записывает заметки в `/data/notes.json`. Хранилище требует
внутренний токен; шлюз получает его из файла, а не из исходного кода.

```text
Клиент → gateway → store → notes.json
```

Образ — подготовленная файловая система с приложением. Контейнер — запущенный
экземпляр этого образа. Dockerfile описывает сборку образа; файлы Compose
описывают запуск и ограничения двух сервисов. В Kubernetes Deployment
управляет Pod, Service даёт внутренний адрес сервиса, NetworkPolicy
ограничивает соединения, а RBAC задаёт права обращения к Kubernetes API.

| Часть проекта | Для чего она нужна |
|---|---|
| `app/app.py` | Чтение и создание заметок, проверка токена, журнал запросов |
| `app/probe.py` | Проверка UID, прав записи, параметров процесса и HTTP |
| `Dockerfile` | Общий образ на Python 3.12.11, пользователь 10001 |
| `compose.baseline.yaml` | Обычный Docker-вариант с UID 0 и записью в rootfs |
| `compose.hardened.yaml` | Усиленный Docker-вариант и его ограничения |
| `compose.cluster.yaml` | Узел K3s в Docker, шифрование Secrets, локальный API |
| `k8s/baseline.yaml` | Обычные Deployment, Service и ServiceAccount |
| `k8s/hardened.yaml` | Усиленные Deployment, шесть NetworkPolicy и RBAC |
| `k8s/probe.*.yaml` | Посторонний Pod `outsider` для проверки изоляции |
| `k8s/reader.*.yaml` | Разрешённый Pod `reader` для проверки приложения |
| `scripts/deploy.py` | Подготовка и развёртывание всего стенда |
| `scripts/verify.py` | 41 сравнительная проверка и сохранение наблюдений |
| `scripts/update_manifest.py` | Обновление сумм файлов после правок и новых измерений |

В Docker шлюзы доступны только с этого компьютера:

| Вариант | Адрес |
|---|---|
| Обычный | `http://127.0.0.1:18081/notes` |
| Усиленный | `http://127.0.0.1:18080/notes` |

В Kubernetes обычные объекты находятся в `article-baseline`, усиленные —
в `article-secure`. Разрешённая цепочка — `reader → gateway → store`.
Под `outsider` должен достигать хранилища в обычном варианте и получать
тайм-аут в усиленном. Схема находится в `evidence/project-topology.jpg`.

Приложение учебное: в шлюзе нет TLS и пользовательской аутентификации.
Допускается не более 100 заметок по 160 символов, тело запроса — до 4096 байт.
В Docker данные находятся в именованных томах; в Kubernetes `emptyDir`
сохраняет их при перезапуске контейнера внутри того же Pod, но теряет при
замене Pod. Повторный `deploy.py` перезапускает Deployment, поэтому
заметки Kubernetes могут исчезнуть. Контейнер узла K3s использует privileged;
усиленные контейнеры приложения так не запускаются.

## 4 Что проверять вручную

### Состояние контейнеров и Pod

```bash
docker compose -p csl-baseline -f compose.baseline.yaml ps
docker compose -p csl-hardened -f compose.hardened.yaml ps
docker compose -p csl-cluster -f compose.cluster.yaml ps
docker exec csl-k3s /bin/kubectl get pods -n article-baseline
docker exec csl-k3s /bin/kubectl get pods -n article-secure
```

В каждом варианте Docker должны работать `gateway` и `store` с состоянием
healthy. В каждом пространстве Kubernetes должны быть готовы Pod шлюза,
хранилища, `reader` и `outsider`. Контейнер узла — `csl-k3s`.

### Чтение и создание заметки

Откройте адрес `/notes` в браузере: появится JSON с `notes` и `count`.
Для создания заметки выполните:

```bash
curl -i -H 'Content-Type: application/json' -d '{"text":"Проверка проекта"}' http://127.0.0.1:18080/notes
curl http://127.0.0.1:18080/notes
```

Первый запрос должен вернуть HTTP 201 и новую заметку, второй — список
с этой заметкой. Для обычного варианта замените порт на `18081`.
Если curl не установлен, ту же последовательность проверяет команда:

```bash
docker exec csl-hardened-gateway-1 python /app/probe.py --notes http://127.0.0.1:8080/notes
```

В её JSON должны быть коды 200, 201 и 200 для `before`, `create` и `after`.

### Права процесса и каталоги

```bash
docker exec csl-baseline-store-1 python /app/probe.py
docker exec csl-hardened-store-1 python /app/probe.py
docker exec csl-k3s /bin/kubectl exec -n article-secure deployment/store -- python /app/probe.py
```

| Поле | Обычный вариант | Усиленный вариант |
|---|---|---|
| `uid` | 0 | 10001 |
| `rootfs_write.allowed` | true | false |
| `data_write.allowed` и `temporary_write.allowed` | true | true |
| `cap_eff` | Ненулевой набор | Все нули |
| `no_new_privs` | `"0"` | `"1"` |
| `service_account_token` в Kubernetes | true | false |
| `docker_socket` | false | false |

Поле `seccomp` равно `"2"` в обоих Docker-вариантах и в усиленном Kubernetes.
В обычном Kubernetes этой проверки для значения `"2"` нет.
Команда выполняет короткие записи в собственные тестовые файлы, а затем
удаляет их. Отказ записи в `/etc` ожидаем для усиленного варианта.

### Разрешённая и запрещённая сеть Kubernetes

Проверьте разрешённого клиента:

```bash
docker exec csl-k3s /bin/kubectl exec -n article-secure reader -- python /app/probe.py http://gateway:8080/notes
```

Ожидается `reachable: true` и `status: 200`. Для постороннего Pod получите
IP хранилища и обратитесь к `/health` напрямую:

```bash
lab_store_ip="$(docker exec csl-k3s /bin/kubectl get pod -n article-secure -l app=store -o jsonpath='{.items[0].status.podIP}')"
docker exec csl-k3s /bin/kubectl exec -n article-secure outsider -- python /app/probe.py "http://${lab_store_ip}:8080/health"
```

Ожидается `reachable: false` с тайм-аутом. Повторите обе строки, заменив
`article-secure` на `article-baseline`: там ожидаются `reachable: true`
и HTTP 200. IP нужно получить заново для другого пространства имён.
Такой опыт проверяет сеть без зависимости от токена и DNS хранилища.

### Права наблюдателя и шифрование

```bash
docker exec csl-k3s /bin/kubectl auth can-i list pods -n article-secure --as=system:serviceaccount:article-secure:notes-observer
docker exec csl-k3s /bin/kubectl auth can-i list secrets -n article-secure --as=system:serviceaccount:article-secure:notes-observer
docker exec csl-k3s /bin/k3s secrets-encrypt status
```

Первые две команды должны вывести `yes` и `no`. У ожидаемого `no` может
быть ненулевой код завершения — это результат запрета. Статус шифрования
должен показывать, что оно включено. Сам по себе статус не проверяет
содержимое базы: в `verify.py` отдельно проверяются зашифрованный префикс
записи Secret и отсутствие открытого токена в этой записи.

## 5 Как читать результаты и объяснять работу

| Файл в `evidence/` | Что показывает |
|---|---|
| `checks.json` | Все 41 проверки: условие, ожидание, факт, результат |
| `runtime-snapshots.json` | UID, CapEff, NoNewPrivs, Seccomp, права записи и монтирования |
| `environment.json` | Время измерения, версии среды и идентификаторы образов |
| `admission-rejection.txt` | Отказ сервера при попытке создать запрещённый Pod в dry-run |
| `encryption-status.txt` | Статус шифрования K3s |
| `application-logs.jsonl` | Записанные события запросов без тел заметок и токена |
| `ARTICLE_MAP.md` | Связь материалов проекта с утверждениями статьи |

Успешный результат — `passed: 41`, `total: 41` и `passed: true` у каждой
проверки. Имена проверок на английском совпадают с выводом скрипта.
Запрет сети подтверждается одновременно двумя наблюдениями: `outsider`
заблокирован, а `reader` продолжает читать и создавать заметки через шлюз.
Проверка функциональности также сверяет наличие новой заметки в списке
и увеличение счётчика; одних HTTP-кодов недостаточно.

При демонстрации покажите обычный сервис, затем усиленный. Создайте заметку,
сравните UID и запись в `/etc`, покажите доступ `reader` и отказ `outsider`,
после чего откройте итог `41/41` и таблицу статьи. Основной вывод: выбранные
ограничения реально действуют и сохраняют функцию приложения. Число 41/41
не является процентом безопасности; CVE, атаки на ядро и нагрузочные испытания
этим проектом не исследовались.

Файл `MANIFEST.sha256` позволяет проверить целостность выданного проекта:

```bash
sha256sum -c MANIFEST.sha256
```

У файлов должен отображаться результат `OK`. После изменения README,
исходников или результатов суммы нужно обновить, иначе проверка закономерно
покажет несовпадение. Выполните обновление перед коммитом:

```bash
python3 scripts/update_manifest.py
```

Скрипт пересчитывает суммы исходников, настроек, документации и результатов.
Приватная папка `.runtime/` в список не входит. Совпадение сумм проверяет
целостность файлов, а работоспособность проверяет `verify.py`.

## 6 Как разместить проект на GitHub

### Создать пустой репозиторий

Войдите в GitHub; если аккаунта нет, создайте его и подтвердите email.
Порядок регистрации описан в [документации GitHub](https://docs.github.com/en/account-and-profile/how-tos/account-management/creating-an-account-on-github).

Откройте [форму создания репозитория](https://github.com/new?name=container-security-lab),
выберите владельцем свой аккаунт и имя `container-security-lab`. В Description
вставьте: «Учебный проект по безопасности Docker и Kubernetes с двумя
конфигурациями и 41 проверкой». Для доступной читателям статьи ссылки
выберите Public. Оставьте выключенным создание README и не добавляйте
шаблон .gitignore или лицензию на этом шаге: README и .gitignore уже есть
в проекте. Нажмите Create repository. Это последовательность для нового
пустого репозитория, описанная в [GitHub Docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository).

В репозиторий загружаются распакованные файлы проекта. Если загрузить только
ZIP, на главной странице не будет привычного просмотра исходников и README.

### Войти из терминала

Для публикации понадобятся Git и GitHub CLI. На компьютере, где готовился
проект, оба уже доступны; на другом компьютере сначала проверьте:

```bash
git --version
gh --version
```

Войдите через браузер:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
```

Первую команду завершите по подсказкам: откройте указанную страницу,
введите одноразовый код и разрешите вход. Вторая настраивает Git для
использования этого входа. Это штатный способ
[авторизации GitHub CLI](https://cli.github.com/manual/gh_auth_login) и
[настройки Git](https://cli.github.com/manual/gh_auth_setup-git).

### Подготовить файлы

Из корня распакованного проекта выполните:

```bash
git init -b main
git config user.name "ВАШЕ ИМЯ"
git config user.email "ВАШ_EMAIL"
```

Имя и email относятся к авторству коммитов и не заменяют вход в GitHub.
Укажите email, привязанный к аккаунту, либо свой адрес noreply из настроек
GitHub. Эти команды задают данные только для данного проекта.

В README замените поле адреса репозитория на реальную ссылку. В статье
пока оставьте поле URL версии: сам тег будет создан ниже. Подготовьте файлы
и проверьте список:

```bash
python3 scripts/update_manifest.py
git add .
git status --short
git diff --cached --stat
git ls-files .runtime
```

Последняя команда должна вывести пустой результат. В списке должны быть
`app`, `k8s`, `scripts`, `docs`, `evidence`, YAML-файлы, `Dockerfile`, README,
`.gitignore` и `.dockerignore`. `.runtime/` содержит локальные секреты и
копию базы; её исключает .gitignore. Не добавляйте её принудительно.

Если `.runtime` всё же оказалась в списке до первого коммита, уберите её
из подготовленных файлов, сохранив локальные данные:

```bash
git rm -r --cached --ignore-unmatch .runtime
```

### Отправить первый коммит

```bash
git commit -m "Учебный стенд Docker и Kubernetes"
git remote add origin https://github.com/ВАШ_ЛОГИН/container-security-lab.git
git remote -v
git push -u origin main
```

Замените `ВАШ_ЛОГИН` именно на логин владельца созданного репозитория.
После успешного push обновите страницу GitHub. В корне должны отображаться
папки и файлы проекта, а ниже — README со схемой и ссылкой на этот гайд.
Эти шаги соответствуют [публикации локального проекта через Git](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

В панели About добавьте темы `docker`, `kubernetes`, `container-security`,
`python` и `student-project`. Описание проекта уже подготовлено выше.

### Сохранить версию для статьи

После публикации правильных исходников, документации и результатов создайте тег:

```bash
git tag -a v1.0.0 -m "Версия проекта для статьи"
git push origin v1.0.0
```

На GitHub откройте Releases → Draft a new release. Выберите существующий
тег `v1.0.0`, задайте название «Версия проекта для статьи 1.0.0» и описание:
«Сервис заметок, обычная и усиленная конфигурации Docker и Kubernetes,
протокол 41/41 проверок, инструкция по воспроизведению». Нажмите Publish release.
GitHub добавит архивы исходников этой версии. Порядок описан в
[руководстве по релизам](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Версия, на которую ссылается статья, должна оставаться прежней. Следующие
изменения публикуйте в main, а для новой версии используйте другой тег.
В обычной конфигурации Git тег можно переместить; поэтому дополнительно
сохраните идентификатор коммита версии:

```bash
git rev-list -n 1 v1.0.0
```

### Обновлять проект в дальнейшем

```bash
python3 scripts/update_manifest.py
git add .
git diff --cached --stat
git commit -m "Обновление проекта"
git push
```

После повторных измерений `evidence/` изменится. Публикуйте результаты вместе
с кодом и настройками, для которых они получены. Если проверка не пройдена,
сначала разберитесь с её причиной, затем фиксируйте версию для статьи.

## 7 Как сослаться на GitHub в статье

### HTML-демонстрация на GitHub Pages

Папка `docs` содержит готовую страницу `index.html`. Для просмотра на своём
компьютере откройте её в браузере, сохранив рядом `style.css`, JavaScript-файлы
и остальные файлы этой папки. Можно также запустить локальный просмотр:

```bash
python3 -m http.server 8088 --directory docs --bind 127.0.0.1
```

Откройте `http://127.0.0.1:8088/`. Чтобы остановить просмотр, нажмите Ctrl+C
в терминале, где работает эта команда. Docker для самой HTML-страницы не нужен.

Для публикации на GitHub откройте Settings → Pages. В Source выберите
Deploy from a branch, затем ветку `main` и папку `/docs`, нажмите Save.
После завершения публикации адрес будет иметь вид
`https://ВАШ_ЛОГИН.github.io/container-security-lab/`. В папке есть `.nojekyll`:
страница использует обычные HTML, CSS и JavaScript, без генератора сайта.
Схема настройки описана в
[документации GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

GitHub Pages размещает статическую страницу. Заметки в демонстрации сохраняются
в браузере; опыты с правами и сетью — модель поведения конфигурации.
Протокол 41 проверки взят из настоящего запуска Docker и Kubernetes.
Сама страница не запускает кластер и не выполняет новые измерения.

После нового запуска `verify.py` обновите данные демонстрации и суммы:

```bash
python3 scripts/build_demo.py
python3 scripts/update_manifest.py
```

Затем сохраните изменения коммитом и отправьте их на GitHub. Чтобы ссылка
«Исходники» на странице вела на ваш репозиторий, укажите его URL в
`docs/site-config.js`, в поле `repository`.

### Библиографическая ссылка

В тексте статьи используйте ссылку `[1]` после утверждений, которые
подтверждаются проектом. Полные листинги оставьте в репозитории; в статье
достаточно схемы, таблицы наблюдений и пояснений результатов.

В статье источник № 1 отсылает к GitHub-версии проекта. Для вашего
репозитория используется адрес ниже; при публикации копии замените логин:

```text
https://github.com/ВАШ_ЛОГИН/container-security-lab/tree/v1.0.0
```

Откройте ссылку в браузере и проверьте наличие README, исходников и `evidence/`.
Запись оформлена в форме электронного ресурса по ГОСТ 7.1—2003, который указан
в правилах конференции. При обращении к новой версии обновите дату. Запись для статьи:

> 1. Container Security Lab [Электронный ресурс] : учебный проект Docker и Kubernetes / archeemage-hub. — Версия 1.0.0. — Электрон. дан. и прогр. — GitHub, 2026. — Режим доступа: https://github.com/archeemage-hub/container-security-lab/tree/v1.0.0 (дата обращения: 13.10.2026). — Загл. с экрана.

Для максимально точной привязки вместо `v1.0.0` в URL можно использовать
полный идентификатор коммита из предыдущего раздела. Он фиксирует содержимое
даже при последующих изменениях ветки. Для отдельного файла GitHub также
позволяет получить постоянную ссылку клавишей `y`; это описано в
[документации о постоянных ссылках](https://docs.github.com/en/repositories/working-with-files/using-files/getting-permanent-links-to-files).

Название версии в статье и тег должны совпадать. Тег репозитория `v1.0.0`
и имя образа приложения `container-security-lab:1.0` — разные обозначения;
переименовывать образ ради тега Git не требуется. После заполнения URL
и авторской шапки ещё раз проверьте, что статья занимает 5–7 страниц.

## 8 Если что-то не работает

| Что произошло | Что сделать |
|---|---|
| `docker: command not found` или нет Compose | Установить Docker Engine и плагин Compose для своей системы |
| Client есть, Server недоступен | Запустить Docker; проверить доступ текущего пользователя |
| Базовый образ отсутствует | Выполнить закреплённый `docker pull` из раздела 2 |
| Порт 18080, 18081 или 16443 занят | Посмотреть `ss -ltnp`; определить процесс, который занимает порт |
| Узел K3s не стал Ready | Проверить свободную память и `docker logs --tail 100 csl-k3s` |
| Pod не готов или `ImagePullBackOff` | Посмотреть `kubectl describe` и повторить `deploy.py`, который импортирует образ |
| `/notes` вернул 503 | Проверить store, его готовность, токен и журналы шлюза |
| POST вернул 400 | Проверить JSON и строку `text` длиной 1–160 символов |
| POST вернул 413 | Проверить размер тела запроса; предел 4096 байт |
| POST вернул 409 | Хранилище достигло 100 заметок; для нового опыта нужен сброс данных |
| `verify.py` пишет FAIL | Найти строку проверки и значения actual/expected в `evidence/checks.json` |
| Проверка остановилась с traceback | Прочитать вывод терминала; текущий `checks.json` может остаться от предыдущего завершённого запуска |
| Git пишет `remote origin already exists` | Посмотреть `git remote -v`; при неверном адресе выполнить `git remote set-url origin НУЖНЫЙ_URL` |
| GitHub пишет `Repository not found` | Проверить логин, имя, существование репозитория и аккаунт входа |
| GitHub пишет `non-fast-forward` | Проверить, не созданы ли в удалённом репозитории отдельные коммиты; для этого гайда нужен пустой репозиторий, без force push |

Полезные команды для диагностики приложения:

```bash
docker logs --tail 50 csl-hardened-gateway-1
docker logs --tail 50 csl-hardened-store-1
docker exec csl-k3s /bin/kubectl get events -n article-secure --sort-by=.metadata.creationTimestamp
docker exec csl-k3s /bin/kubectl describe deployment store -n article-secure
docker exec csl-k3s /bin/kubectl logs -n article-secure deployment/store --tail=50
```

Если скрипт упал, не считайте старый файл результатов подтверждением текущего
запуска. После устранения причины выполните `deploy.py`, затем `verify.py`
и дождитесь нового итогового сообщения.

## 9 Остановка и новый опыт

Остановить стенд, сохранив Docker-тома и состояние кластера:

```bash
docker compose -p csl-baseline -f compose.baseline.yaml stop
docker compose -p csl-hardened -f compose.hardened.yaml stop
docker compose -p csl-cluster -f compose.cluster.yaml stop
```

Для следующего запуска снова выполните `python3 scripts/deploy.py`.
Если нужен новый опыт с пустыми хранилищами, следующие команды удалят
именно данные этого стенда и сам локальный кластер:

```bash
docker compose -p csl-baseline -f compose.baseline.yaml down -v
docker compose -p csl-hardened -f compose.hardened.yaml down -v
docker compose -p csl-cluster -f compose.cluster.yaml down -v
```

Затем выполните `deploy.py` и `verify.py`. Локальный токен в `.runtime/`
может использоваться повторно; он по-прежнему не входит в Git. Команды
глобальной очистки Docker для этого проекта не нужны.
