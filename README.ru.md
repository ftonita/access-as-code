# access-as-code

[English](README.md) | **Русский**

[![ci](https://github.com/ftonita/access-as-code/actions/workflows/ci.yml/badge.svg)](https://github.com/ftonita/access-as-code/actions)
![Vault](https://img.shields.io/badge/Vault-policies-FFEC6E?logo=vault&logoColor=black)
![Kubernetes](https://img.shields.io/badge/Kubernetes-RBAC-326CE5?logo=kubernetes&logoColor=white)
![GitLab](https://img.shields.io/badge/GitLab-members-FC6D26?logo=gitlab&logoColor=white)

**Опишите, кто и что может делать, в одном проверяемом YAML-файле. Проверьте его правилами минимальных привилегий, скомпилируйте в политики Vault, Kubernetes RBAC и членство в GitLab и находите расхождения с тем, что реально настроено.**

Доступы, выданные кликами в интерфейсах, нельзя отревьюить, сравнить или проверить при аудите. Здесь каждое изменение - это merge request: ревьюеры видят, какой человек получает какую роль в какой команде и окружении, CI отклоняет рискованные выдачи, а один и тот же файл порождает конфигурацию для всех трёх систем.

> **Все люди, команды, тикеты и тенанты вымышлены.** Это референсный дизайн модели минимальных привилегий, а не данные или код какого-либо работодателя.

## Быстрый старт (10 минут)

Нужен Python 3.10+. Пакета в PyPI пока нет, ставим из клона репозитория:

```bash
git clone https://github.com/ftonita/access-as-code.git && cd access-as-code
python -m venv .venv && source .venv/bin/activate
pip install -e .

access-as-code init --out access          # стартовые файлы в ./access (common.yml + файл команды)
access-as-code lint access                # код 0 = OK, 1 = нарушения правил, 2 = некорректный вход
access-as-code matrix access              # у кого какие роли и где, одним взглядом
access-as-code compile access --out build # то, что применится к Vault / Kubernetes / GitLab
```

Или поиграйте с готовым примером - компания, разбитая на два направления: `examples/company/` (чистый, хороший шаблон) и, в прежнем плоском формате, `examples/access.bad.yml` (по одной заложенной проблеме на правило).
Lint упал? `access-as-code explain AAC003` объяснит, как исправить правило.

**Кто что правит?** Техподдержка правит YAML по [шпаргалке](docs/SUPPORT.ru.md) (готовые рецепты для типовых заявок). Безопасность владеет `common.yml`. Руководитель направления ревьюит свой файл. Остальное делает CI.

## Модель: один экран на команду

```yaml
# web.yml - направление "web"
version: 2
teams:
  sites:
    members:                                 # все люди команды: логин -> корпоративная почта
      alice: alice@corp.example
      bob: bob@corp.example
    access:                                  # что получает КАЖДЫЙ участник, по окружениям
      dev: developer
      stage: developer
      prod: { role: viewer, ticket: SEC-101 }
    extra:                                   # разовый / временный доступ
      - { who: alice, role: deployer, env: prod, ticket: SEC-110, expires: 2026-12-15 }
      - { who: [bob, carol], role: viewer, env: stage }
```

| Понятие | Смысл |
|---|---|
| **role** | именованный набор прав для каждой системы (задаётся один раз в `common.yml`): «developer» означает одно и то же в Vault, Kubernetes и GitLab |
| **members** | люди команды. Удалили имя - командный доступ отозван; перенесите имя в `left:`, чтобы lint нашёл забытые строки в `extra` |
| **access** | матрица команды: окружение -> роль (или `{ role, ticket }`). Действует на каждого участника |
| **extra** | индивидуальные выдачи: `who` (имя или список), `role`, `env`, необязательные `ticket`, `expires`, `reason`. Строку пишет команда, которой принадлежит ресурс, даже если человек из другой команды |

```yaml
    members:                       # логин: корпоративная почта
      alice: alice@corp.example
      bob: bob@corp.example
```

Практические правила: в production всегда нужен `ticket`; выдача человеку в production требует `expires` (максимум 90 дней); опасная роль `break-glass` требует оба поля и срок не более 7 дней.

## Разбиение на файлы по направлениям

Передайте **каталог** - все `*.yml` в нём объединяются, так что у каждого направления свой файл и свои ревьюеры:

```text
access/
  common.yml   # environments, production_environments, roles                  владелец: безопасность
  web.yml      # teams: sites, portal                                          владелец: руководители web
  infr.yml     # teams: devops, sys-adm                                        владелец: руководители инфры
```

* Команды принимают файл или каталог: `access-as-code lint access/`.
* Команда, человек, группа или роль определяются **ровно один раз**, в одном файле; повторное определение - ошибка с именами обоих файлов. Окружения и `production_environments` объединяются.
* Порядок файлов не важен. В сообщениях есть имя файла: `AAC003 error: grant #4 (...) [web.yml]: production grant without a ticket`.
* Доступ «через направления» пишется в файле владельца ресурса: если alice (web) нужен stage в devops, запись идёт в `devops.extra` файла `infr.yml`. Её согласуют руководители инфры (см. [examples/CODEOWNERS](examples/CODEOWNERS)); без тикета lint предупредит о межкомандном доступе (AAC008).
* Файлы в каталоге должны быть `version: 2`. Небольшой компании можно держать всё в одном файле (`common` + команды).
* Помощь редактора: каждый пример начинается с `# yaml-language-server: $schema=...`; схема лежит в [schema/access.v2.schema.json](schema/access.v2.schema.json) (`access-as-code schema` её перегенерирует), поэтому VS Code / JetBrains с YAML-плагином подсказывают и подчёркивают ошибки прямо при вводе.

## Команды

`PATH` - файл или каталог.

| Команда | Что делает | Код возврата |
|---|---|---|
| `init [--out access]` | стартовые файлы (каталог; один файл, если `--out` оканчивается на `.yml`); ничего не перезаписывает | 0 / 2 |
| `validate PATH` | только схема и структура | 0 / 2 |
| `lint PATH [--strict] [--format text, json or github]` | правила минимальных привилегий; `--strict` падает и на предупреждениях; `github` печатает аннотации, привязанные к файлу в PR | 0 / 1 |
| `explain AAC003` | что значит правило и как его исправить | 0 / 2 |
| `matrix PATH` | таблица команда x окружение: какие роли и сколько людей | 0 |
| `who PATH PERSON` | весь действующий доступ человека, откуда он взялся, тикеты и сроки | 0 / 2 |
| `changes BASE HEAD [--format text, markdown or json]` | кто получил или потерял доступ между двумя каталогами (например, базовая ветка и PR), плюс учётные записи для создания и удаления | 0 / 2 |
| `compile PATH [--out build]` | пишет артефакты Vault / Kubernetes / GitLab и `people.json` | 0 |
| `export-state PATH --vault --kubernetes --gitlab [--out snapshot.json]` | экспорт фактического состояния из живых систем (только чтение) | 0 / 2 |
| `diff PATH --actual snapshot.json` | желаемое состояние против фактического (секции, которых нет в снимке, помечаются как непроверенные) | 0 нет дрейфа / 1 дрейф |
| `review PATH [--days 30]` | истекающие и повышенные выдачи | 0 |
| `schema` | JSON Schema файлов версии 2 (проверка в редакторе) | 0 |
| `rules` | список правил | 0 |
| `demo-state PATH [--out actual.json]` | генерирует «дрейфующий» снимок для экспериментов | 0 |

Все команды, зависящие от времени, принимают `--today YYYY-MM-DD` (по умолчанию - текущая дата). Код 2 означает, что вход не прочитан или не прошёл схему; сообщение называет файл и точный путь, например `web.yml: teams.sites.extra[1]: 'env' is a required property`.

> **Даты в примерах.** Выдачи в примерах истекают в октябре-декабре 2026. Запускайте их с `--today 2026-10-08` (как делают этот README и CI), иначе позже они начнут падать как «просроченные».

## Повседневные сценарии

Полные версии для копирования с сообщениями CI - в [docs/SUPPORT.ru.md](docs/SUPPORT.ru.md). Коротко: любая заявка - небольшая правка блока одной команды:

| В заявке сказано... | Правка |
|---|---|
| Новый сотрудник | добавить `логин: почта` в `members` команды (на этот адрес уйдут данные его учётной записи) |
| Сотрудник уволился | перенести имя из `members` в `left`; удалить его строки в `extra` |
| Временный доступ в prod | строка в `extra` с `ticket` и `expires` |
| Аварийный доступ | то же с ролью `break-glass`, `expires` в пределах 7 дней, `reason` |
| Продлить / убрать доступ | изменить `expires` / удалить строку |
| Новая команда | блок в `teams:` (в файле её направления; должны существовать mount Vault `kv-<team>` и namespace'ы Kubernetes `<team>-<env>`) |
| Новая роль | добавляет безопасность в `common.yml` |

## Соглашения, на которые опирается инструмент

* **Имена** (`teams`, `environments`, роли, люди, группы) - строчные буквы, цифры и дефисы.
* **Базовый доступ команды = группа `<team>-team`.** Версия 2 превращает `members` + `access` в группу с таким именем (в сообщениях lint видна как `group:sites-team`); не задавайте группу с таким именем сами.
* **id человека = логин в целевых системах.** Он становится именем `User` в RoleBinding Kubernetes (ваш OIDC username), участником групп Vault identity и ключом в GitLab `members.json`. Если в вашем IdP логин `a.smith`, переименуйте или сделайте маппинг на шаге применения.
* **Именование целей:** политика/группа Vault `<team>-<env>-<role>`, путь KV `kv-<team>/data|metadata/<env>/*`, namespace Kubernetes `<team>-<env>`, RoleBinding `aac-<level>` на встроенную ClusterRole `view`/`edit`/`admin`.
* **AAC007 сопоставляет имена ролей** `deployer` и `approver`. Если роли названы иначе, правило не сработает (см. `SOD_ROLES` в `src/access_as_code/lint.py`).
* Выдача группе даёт роль каждому участнику; две выдачи одному человеку в одном месте объединяются (побеждает высший уровень GitLab/Kubernetes, в Vault - одна политика на роль).

## Правила lint (`access-as-code rules`)

| ID | Уровень | Правило |
|---|---|---|
| AAC001 | error | Ни одна роль не может иметь право Vault `sudo`. |
| AAC002 | error | Выдачи ссылаются на известные команды, окружения, роли и субъекты (группы - на известных людей, люди - на известные команды). |
| AAC003 | error | Выдачи в production требуют тикет; прямые выдачи человеку - ещё и срок (максимум 90 дней). |
| AAC004 | error | Повышенные роли (`delete` / Kubernetes `admin`) в production требуют тикет и срок до 7 дней. |
| AAC005 | error | Уволенные не имеют доступа ни напрямую, ни через группу. |
| AAC006 | error | Просроченные выдачи нужно удалять. |
| AAC007 | error | Разделение обязанностей: никто не может быть и `deployer`, и `approver` в одной команде в production, даже через группы. |
| AAC008 | warning | Межкомандный доступ требует тикет. |
| AAC009 | warning | Дубликаты выдач. |
| AAC010 | info | Неиспользуемые роли и группы. |
| AAC011 | warning | Выдачи, истекающие в течение 14 дней, пора пересмотреть. |
| AAC012 | error | При `require_email: true` у каждого активного человека есть корпоративная почта. |
| AAC013 | error | Два человека не делят один адрес почты. |
| AAC014 | error | При `email_domains` адреса принадлежат одному из перечисленных доменов. |

`lint` возвращает 1 при ошибках (`--strict`: и при предупреждениях), поэтому подходит как обязательная проверка merge request. `--today` фиксирует дату для воспроизводимых запусков.

## Разбор на встроенных синтетических данных

```text
$ access-as-code lint examples/access.bad.yml --today 2026-10-08
AAC001 error: role 'super-ops' grants the Vault 'sudo' capability
AAC003 error: grant #3 (bob -> deployer on payments/prod): direct production grant without an expiry
AAC005 error: grant #0 (group:payments-devs -> developer on payments/dev): 'gone' is offboarded
AAC007 error: 'alice' is both deployer and approver on payments/prod
...
14 error(s), 5 warning(s), 3 info                                   (exit 1)

$ access-as-code lint examples/company --today 2026-10-08
AAC011 warning: grant #5 (erin -> break-glass on devops/prod) [infr.yml]: expires on 2026-10-12
0 error(s), 1 warning(s), 0 info                                    (exit 0)

$ access-as-code matrix examples/company --today 2026-10-08
team     dev           stage                    prod
devops   developer x2  developer x2             approver x1, break-glass x1, deployer x1, viewer x2
sys-adm  developer x2  developer x2             approver x1, deployer x1, viewer x2
sites    developer x2  developer x2, viewer x1  approver x1, deployer x1, viewer x2
portal   developer x2  developer x2             approver x1, deployer x1, viewer x2

$ access-as-code who examples/company carol --today 2026-10-08
carol: team portal, active
  portal/dev  developer  via group:portal-team  ticket=-  expires=-
  portal/prod  deployer  via direct  ticket=SEC-112  expires=2026-12-01
  portal/prod  viewer  via group:portal-team  ticket=SEC-102  expires=-
  portal/stage  developer  via group:portal-team  ticket=-  expires=-
  sites/stage  viewer  via direct  ticket=SEC-130  expires=-

$ access-as-code compile examples/company --today 2026-10-08 --out build
wrote 39 files to build
```

Сгенерировано, например, `build/vault/policies/sites-prod-deployer.hcl`:

```hcl
path "kv-sites/data/prod/*" {
  capabilities = ["create", "read", "update"]
}

path "kv-sites/metadata/prod/*" {
  capabilities = ["list", "read"]
}
```

а также `vault/groups.json` (identity-группа -> политика + участники), по одному Kubernetes `RoleBinding` на namespace и уровень (`sites-dev` / `edit`) и `gitlab/members.json` (наивысший уровень на человека в команде).

**`compile` выдаёт только действующий доступ**: просроченные выдачи, уволенные и некорректные выдачи не попадают в результат, даже если lint пропустили.

### Дрейф (drift)

```text
$ access-as-code diff examples/company --today 2026-10-08 --actual actual.json
changed  vault_policies:devops-dev-developer  content differs
extra    vault_policies:legacy-admin  configured but not declared
changed  vault_groups:devops-dev-developer  missing members ['erin']
changed  vault_groups:devops-prod-break-glass  extra members ['zed']
missing  kubernetes:devops-dev/edit  declared but not configured
changed  gitlab:sites  carol: declared 'reporter', actual 'maintainer'
6 difference(s)                                                      (exit 1)
```

### Экспорт фактического состояния из живых систем

```bash
export VAULT_ADDR=https://vault.example.com VAULT_TOKEN=...      # нужны list/read на sys/policies/acl и identity/*
export GITLAB_URL=https://gitlab.example.com GITLAB_TOKEN=...     # scope read_api, членство в группах команд
access-as-code export-state access --vault --kubernetes --gitlab --out snapshot.json
access-as-code diff access --actual snapshot.json
```

* **Только чтение**: GET/LIST-запросы и `kubectl get`. Токены берутся из окружения и не попадают в снимок. Используйте отдельный токен только на чтение.
* **Vault**: все ACL-политики кроме `default`/`root` и все identity-группы с *именами* сущностей (имя entity должно совпадать с id человека). Учитывается `VAULT_CACERT`.
* **Kubernetes**: `kubectl` с текущим контекстом. По умолчанию читаются только RoleBinding с меткой `managed-by=access-as-code` (их создаёт `compile`); `--k8s-all` добавляет и созданные вручную привязки к `view`/`edit`/`admin`.
* **GitLab**: *прямые* участники группы `<prefix><team>` (`--gitlab-group-prefix 'acme/'`); уровни guest/owner выгружаются как есть, поэтому owner виден как дрейф. Команда без группы считается отсутствующей (missing).
* * Безопасность: нужен HTTPS (простой `http://` только для localhost), редиректы не выполняются, `VAULT_NAMESPACE` учитывается. Участник группы с удалённой entity в Vault виден как `<unknown-entity:id>`; субъекты Group/ServiceAccount в Kubernetes выводятся как `group:<name>` / `serviceaccount:<ns>:<name>`, поэтому избыточные права видны как лишние участники; унаследованные (из родительской группы) участники GitLab не выгружаются.
* Отсутствующая группа GitLab - ошибка (неверный префикс или токен?), если не указан `--gitlab-missing-ok`.
* Указывайте только те системы, до которых есть доступ: остальные выводятся как `not checked`, а не как дрейф.

Покрыто тестами на поддельных Vault/GitLab и поддельном `kubectl`, **но не на реальных инсталляциях**.

Чтобы воспроизвести пример без живых систем: `access-as-code demo-state examples/company --today 2026-10-08 --out actual.json` генерирует правдоподобные ручные правки. В реальной работе вы по расписанию выгружаете те же четыре секции из своих систем и роняете задачу при любом различии. Проще всего изучить формат так: `compile` пишет «желаемую» сторону, а `demo-state` - полный пример снимка. Форма снимка:

```json
{
  "vault_policies": { "sites-dev-developer": "<текст HCL, как в build/vault/policies/*.hcl>" },
  "vault_groups":   { "sites-dev-developer": ["alice", "bob"] },
  "kubernetes":     { "sites-dev/edit": ["alice", "bob"] },
  "gitlab":         { "sites": { "alice": "maintainer" } }
}
```

Снимок без единой из четырёх секций отклоняется (код 2). Секция, которой нет в снимке, не проверяется; пустая (`{}`) означает «ничего не настроено» и даёт missing по всему объявленному.

## Рекомендуемый процесс

1. Каталог `access/` лежит в репозитории с CODEOWNERS: свой владелец на каждый файл (безопасность - `common.yml`, руководители направления - свой файл).
2. Merge request: CI запускает `lint` (блокирующий) и показывает `review`.
3. После слияния: `compile`, применение вашими средствами (провайдер Terraform для Vault, `kubectl apply`, GitLab API).
4. Ночью: `export-state`, затем `diff`; алерт при дрейфе.

## Корпоративная почта и персональная доставка данных учётных записей

Для части систем нужны **локальные учётные записи** (userpass в Vault, локальные пользователи GitLab, клиентские сертификаты Kubernetes...). Чтобы создавать их, не храня в репозитории ни пароль, ни токен, ни иной секрет, у человека есть корпоративный адрес, а автоматизация отправляет данные для входа на эту почту - лично и один раз:

```yaml
# common.yml
require_email: true                 # AAC012: у каждого активного человека должен быть адрес
email_domains: [corp.example]       # AAC014: и только корпоративный
# web.yml
    members:
      alice: alice@corp.example     # логин: адрес (bob: без адреса допустим, пока не включён require_email)
```

* `compile` пишет **`people.json`**: для каждого человека с действующим доступом там `email`, `team`, `systems`, где нужна учётная запись (`vault`, `kubernetes`, `gitlab`, выводятся из ролей), и `access`, который он получает. **Секретов в нём нет.** Новая команда `changes` в PR перечисляет **учётные записи для создания** и **больше не нужные**, чтобы автоматизация знала, кого заводить и удалять.
* Шаг отправки - ваш (нужны ваш почтовый релей и ваш инструмент создания УЗ), а этот инструмент пароли не обрабатывает. Рекомендуемая схема: сгенерировать одноразовый пароль или ссылку-приглашение/сброса, отправить из пайплайна на `people.json` -> `email`, потребовать смену при первом входе и не оставлять секрет ни в логе, ни в артефакте, ни в переменной.
* Lint защищает адресата: приватный домен (AAC014) или ящик, общий для двух людей (AAC013), роняет PR, а сообщения называют человека, но не адрес. Адрес - персональные данные: держите репозиторий доступов **приватным** и считайте `people.json` конфиденциальным.

## Проверка pull request (GitHub Actions)

Скопируйте [examples/ci/github-actions.yml](examples/ci/github-actions.yml) в `.github/workflows/access.yml` репозитория доступов (5 строк настройки). Он вызывает переиспользуемый workflow [.github/workflows/access-check.yml](.github/workflows/access-check.yml), который для каждого PR, затрагивающего `access/`:

* проверяет схему и lint; находки видны как **аннотации у нужного файла** и блокируют слияние (`strict: true` блокирует и по предупреждениям);
* пишет **сводку задания**: матрица команда x окружение, истекающие и повышенные выдачи, **кто получил или потерял доступ** (и какие УЗ создать или удалить) и `diff` сгенерированной конфигурации Vault / Kubernetes / GitLab между базовой веткой и PR - ревьюер видит, что реально изменит слияние;
* проверяет, что каталог компилируется. Задание только читает и не требует секретов (`permissions: contents: read`).

Сделайте проверку **обязательной** (branch protection / ruleset) и добавьте CODEOWNERS, чтобы файл каждого направления требовал одобрения его руководителей. В этом репозитории она применяется к самому себе в `.github/workflows/access-pr.yml`. Закрепите ссылку в `uses:` на тег или SHA коммита, если хотите сами управлять обновлениями.

## Плоский формат (версия 1)

Прежний однофайловый формат (`version: 1`: `people`, `groups` и список `grants` с полями `subject`, `role`, `team`, `env`) по-прежнему поддерживается и даёт точно такой же результат; см. `examples/access.yml` и `examples/access.bad.yml`. Для нового лучше использовать версию 2: она короче и делится по направлениям. Внутри оба формата превращаются в одну модель.

## FAQ

* **`error: ... is a required property`** - файл не прошёл схему; `access-as-code validate` выводит все проблемы с путями.
* **Lint проходит локально, но падает в CI** - дело в датах: зафиксируйте обе стороны через `--today` или исправьте выдачу, которая вот-вот истечёт (AAC011 предупреждает за 14 дней).
* **`compile` меняет мои системы?** Нет. Он только пишет файлы; применять их (Terraform, `kubectl apply`, GitLab API) - ваш шаг.
* **Можно ли отключить правило для одной выдачи?** Нет, так задумано. Меняйте правило в коде через ревью или исправляйте выдачу.

## Что проверено

Воспроизведение: `pip install -e ".[dev]" && pytest` (106 тестов): каждое правило lint (позитивные, негативные и граничные случаи, например срок ровно через 90 дней или истекающий сегодня), отклонение схемой, разворачивание групп, детерминированная компиляция, исключение просроченного/уволенного доступа, все виды дрейфа, коды возврата CLI.

**Не проверено:** применение результата к реальным Vault, Kubernetes или GitLab; форматы HCL, RoleBinding и уровней участников следуют публичной документации, но в эти системы не загружались. `export-state` проверен только на поддельных сервисах; namespace'ы Vault, отличные от токена, вложенные подгруппы GitLab и унаследованное членство не выгружаются. Пути политик Vault предполагают KV v2 mount с именами `kv-<team>`. Слияние нескольких файлов и разворачивание версии 2 покрыты тестами (повторные определения, порядок файлов, сообщения с именами файлов). Роли действуют на уровне команды и окружения; более тонкое ограничение (отдельные пути, время суток) вне рамок проекта.
