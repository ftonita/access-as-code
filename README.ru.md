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

access-as-code init --out access.yml      # стартовый файл, проходящий lint
access-as-code lint access.yml            # код 0 = OK, 1 = нарушения правил, 2 = некорректный вход
access-as-code compile access.yml --out build
ls -R build                               # то, что применится к Vault / Kubernetes / GitLab
```

Можно обойтись без `init` и поиграть с готовыми файлами: `examples/access.yml` (чистый) и `examples/access.bad.yml` (по одной заложенной проблеме на правило).
Lint упал? `access-as-code explain AAC003` объяснит, как исправить это правило.

**Куда это положить в реальной компании?** В отдельный Git-репозиторий (или каталог) с `access.yml`, CODEOWNERS ([examples/CODEOWNERS](examples/CODEOWNERS)) и CI-задачей ([examples/ci/gitlab-ci.yml](examples/ci/gitlab-ci.yml); для GitHub - `.github/workflows/ci.yml`, задача `access-review`).

## Команды

| Команда | Что делает | Код возврата |
|---|---|---|
| `init [--out access.yml]` | создаёт стартовый файл (не перезаписывает существующий) | 0 / 2 |
| `validate FILE` | только схема и структура | 0 / 2 |
| `lint FILE [--strict] [--format json]` | правила минимальных привилегий; `--strict` падает и на предупреждениях | 0 / 1 |
| `explain AAC003` | что значит правило и как его исправить | 0 / 2 |
| `compile FILE [--out build]` | пишет артефакты Vault / Kubernetes / GitLab | 0 |
| `export-state FILE --vault --kubernetes --gitlab [--out snapshot.json]` | экспорт фактического состояния из живых систем (только чтение) | 0 / 2 |
| `diff FILE --actual snapshot.json` | желаемое состояние против фактического (секции, которых нет в снимке, помечаются как непроверенные) | 0 нет дрейфа / 1 дрейф |
| `review FILE [--days 30]` | истекающие и повышенные выдачи | 0 |
| `rules` | список правил | 0 |
| `demo-state FILE [--out actual.json]` | генерирует «дрейфующий» снимок для экспериментов | 0 |

Все команды, зависящие от времени, принимают `--today YYYY-MM-DD` (по умолчанию - текущая дата). Код 2 означает, что вход не прочитан или не прошёл схему; сообщение называет точный путь, например `grants[3].ticket: 'x' does not match ...`.

> **Даты в примерах.** Выдачи в примерах истекают в октябре-декабре 2026. Запускайте их с `--today 2026-10-08` (как делают README и CI), иначе позже они начнут падать как «просроченные».

## Повседневные сценарии

Всё это - правки `access.yml` в merge request:

| Мне нужно... | Что сделать |
|---|---|
| Принять человека | добавить в `people:` (`team`, `status: active`) и включить в группу, например `payments-devs` |
| Уволить человека | поставить `status: offboarded`, затем удалить его выдачи и членство в группах (пока не сделано, AAC005 падает) |
| Дать доступ в prod под задачу | одна выдача: `{ subject: alice, role: deployer, team: payments, env: prod, ticket: SEC-123, expires: <дата, не позже 90 дней> }` |
| Аварийный доступ | роль с `delete`/Kubernetes `admin` (например `break-glass`), `ticket` и `expires` в пределах 7 дней (AAC004) |
| Продлить доступ | изменить `expires` и `ticket`; просроченные строки не оставлять (AAC006) |
| Добавить команду | добавить в `teams:`, затем людей, группы и выдачи. Для Vault нужен KV v2 mount `kv-<team>`, для Kubernetes - namespace `<team>-<env>` |
| Добавить роль | добавить в `roles:`; систему, где роль ничего не даёт, просто не указывайте |

## Соглашения, на которые опирается инструмент

* **Имена** (`teams`, `environments`, роли, люди, группы) - строчные буквы, цифры и дефисы.
* **id человека = логин в целевых системах.** Он становится именем `User` в RoleBinding Kubernetes (ваш OIDC username), участником групп Vault identity и ключом в GitLab `members.json`. Если в вашем IdP логин `a.smith`, переименуйте или сделайте маппинг на шаге применения.
* **Именование целей:** политика/группа Vault `<team>-<env>-<role>`, путь KV `kv-<team>/data|metadata/<env>/*`, namespace Kubernetes `<team>-<env>`, RoleBinding `aac-<level>` на встроенную ClusterRole `view`/`edit`/`admin`.
* **AAC007 сопоставляет имена ролей** `deployer` и `approver`. Если роли названы иначе, правило не сработает (см. `SOD_ROLES` в `src/access_as_code/lint.py`).
* Выдача группе даёт роль каждому участнику; две выдачи одному человеку в одном месте объединяются (побеждает высший уровень GitLab/Kubernetes, в Vault - одна политика на роль).

## Модель

```yaml
roles:
  developer: { vault: [read, list], kubernetes: edit, gitlab: developer }
  deployer:  { vault: [read, list, create, update], kubernetes: edit, gitlab: maintainer }
  approver:  { gitlab: maintainer }
people:
  alice: { team: payments, status: active }
groups:
  payments-devs: [alice, bob]
grants:
  - { subject: "group:payments-devs", role: developer, team: payments, env: dev }
  - { subject: alice, role: deployer, team: payments, env: prod, ticket: SEC-110, expires: 2026-12-15 }
```

Одна выдача = *субъект* + *роль* + *команда* + *окружение* (+ тикет, срок, причина). Роль - набор прав для каждой системы, поэтому «developer» означает одно и то же в Vault, Kubernetes и GitLab.

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

`lint` возвращает 1 при ошибках (`--strict`: и при предупреждениях), поэтому подходит как обязательная проверка merge request. `--today` фиксирует дату для воспроизводимых запусков.

## Разбор на встроенных синтетических данных

```text
$ access-as-code lint examples/access.bad.yml --today 2026-10-08
AAC001 error: role 'super-ops' grants the Vault 'sudo' capability
AAC003 error: grant #3 (bob -> deployer on payments/prod): direct production grant without an expiry
AAC005 error: grant #0 (group:payments-devs -> developer on payments/dev): 'gone' is offboarded
AAC007 error: 'alice' is both deployer and approver on payments/prod
...
11 error(s), 5 warning(s), 3 info                                   (exit 1)

$ access-as-code lint examples/access.yml --today 2026-10-08
AAC011 warning: grant #10 (bob -> break-glass on payments/prod): expires on 2026-10-12
0 error(s), 1 warning(s), 1 info                                    (exit 0)

$ access-as-code compile examples/access.yml --today 2026-10-08 --out build
wrote 20 files to build
```

Сгенерировано, например, `build/vault/policies/payments-prod-deployer.hcl`:

```hcl
path "kv-payments/data/prod/*" {
  capabilities = ["create", "read", "update"]
}

path "kv-payments/metadata/prod/*" {
  capabilities = ["list", "read"]
}
```

а также `vault/groups.json` (identity-группа -> политика + участники), по одному Kubernetes `RoleBinding` на namespace и уровень (`payments-dev` / `edit`) и `gitlab/members.json` (наивысший уровень на человека в команде).

**`compile` выдаёт только действующий доступ**: просроченные выдачи, уволенные и некорректные выдачи не попадают в результат, даже если lint пропустили.

### Дрейф (drift)

```text
$ access-as-code diff examples/access.yml --today 2026-10-08 --actual actual.json
extra    vault_policies:legacy-admin  configured but not declared
changed  vault_policies:payments-dev-developer  content differs
changed  vault_groups:payments-dev-developer  missing members ['alice']
changed  vault_groups:payments-prod-break-glass  extra members ['zed']
missing  kubernetes:payments-dev/edit  declared but not configured
changed  gitlab:scoring  erin: declared 'developer', actual 'maintainer'
6 difference(s)                                                      (exit 1)
```

### Экспорт фактического состояния из живых систем

```bash
export VAULT_ADDR=https://vault.example.com VAULT_TOKEN=...      # нужны list/read на sys/policies/acl и identity/*
export GITLAB_URL=https://gitlab.example.com GITLAB_TOKEN=...     # scope read_api, членство в группах команд
access-as-code export-state access.yml --vault --kubernetes --gitlab --out snapshot.json
access-as-code diff access.yml --actual snapshot.json
```

* **Только чтение**: GET/LIST-запросы и `kubectl get`. Токены берутся из окружения и не попадают в снимок. Используйте отдельный токен только на чтение.
* **Vault**: все ACL-политики кроме `default`/`root` и все identity-группы с *именами* сущностей (имя entity должно совпадать с id человека). Учитывается `VAULT_CACERT`.
* **Kubernetes**: `kubectl` с текущим контекстом. По умолчанию читаются только RoleBinding с меткой `managed-by=access-as-code` (их создаёт `compile`); `--k8s-all` добавляет и созданные вручную привязки к `view`/`edit`/`admin`.
* **GitLab**: *прямые* участники группы `<prefix><team>` (`--gitlab-group-prefix 'acme/'`); уровни guest/owner выгружаются как есть, поэтому owner виден как дрейф. Команда без группы считается отсутствующей (missing).
* * Безопасность: нужен HTTPS (простой `http://` только для localhost), редиректы не выполняются, `VAULT_NAMESPACE` учитывается. Участник группы с удалённой entity в Vault виден как `<unknown-entity:id>`; субъекты Group/ServiceAccount в Kubernetes выводятся как `group:<name>` / `serviceaccount:<ns>:<name>`, поэтому избыточные права видны как лишние участники; унаследованные (из родительской группы) участники GitLab не выгружаются.
* Отсутствующая группа GitLab - ошибка (неверный префикс или токен?), если не указан `--gitlab-missing-ok`.
* Указывайте только те системы, до которых есть доступ: остальные выводятся как `not checked`, а не как дрейф.

Покрыто тестами на поддельных Vault/GitLab и поддельном `kubectl`, **но не на реальных инсталляциях**.

Чтобы воспроизвести пример без живых систем: `access-as-code demo-state examples/access.yml --today 2026-10-08 --out actual.json` генерирует правдоподобные ручные правки. В реальной работе вы по расписанию выгружаете те же четыре секции из своих систем и роняете задачу при любом различии. Проще всего изучить формат так: `compile` пишет «желаемую» сторону, а `demo-state` - полный пример снимка. Форма снимка:

```json
{
  "vault_policies": { "payments-dev-developer": "<текст HCL, как в build/vault/policies/*.hcl>" },
  "vault_groups":   { "payments-dev-developer": ["alice", "bob"] },
  "kubernetes":     { "payments-dev/edit": ["alice", "bob"] },
  "gitlab":         { "payments": { "alice": "maintainer" } }
}
```

Снимок без единой из четырёх секций отклоняется (код 2). Секция, которой нет в снимке, не проверяется; пустая (`{}`) означает «ничего не настроено» и даёт missing по всему объявленному.

## Рекомендуемый процесс

1. `access.yml` лежит в репозитории с CODEOWNERS (безопасность + тимлиды).
2. Merge request: CI запускает `lint` (блокирующий) и показывает `review`.
3. После слияния: `compile`, применение вашими средствами (провайдер Terraform для Vault, `kubectl apply`, GitLab API).
4. Ночью: `export-state`, затем `diff`; алерт при дрейфе.

## FAQ

* **`error: ... is a required property`** - файл не прошёл схему; `access-as-code validate` выводит все проблемы с путями.
* **Lint проходит локально, но падает в CI** - дело в датах: зафиксируйте обе стороны через `--today` или исправьте выдачу, которая вот-вот истечёт (AAC011 предупреждает за 14 дней).
* **`compile` меняет мои системы?** Нет. Он только пишет файлы; применять их (Terraform, `kubectl apply`, GitLab API) - ваш шаг.
* **Можно ли отключить правило для одной выдачи?** Нет, так задумано. Меняйте правило в коде через ревью или исправляйте выдачу.

## Что проверено

Воспроизведение: `pip install -e ".[dev]" && pytest` (62 теста): каждое правило lint (позитивные, негативные и граничные случаи, например срок ровно через 90 дней или истекающий сегодня), отклонение схемой, разворачивание групп, детерминированная компиляция, исключение просроченного/уволенного доступа, все виды дрейфа, коды возврата CLI.

**Не проверено:** применение результата к реальным Vault, Kubernetes или GitLab; форматы HCL, RoleBinding и уровней участников следуют публичной документации, но в эти системы не загружались. `export-state` проверен только на поддельных сервисах; namespace'ы Vault, отличные от токена, вложенные подгруппы GitLab и унаследованное членство не выгружаются. Пути политик Vault предполагают KV v2 mount с именами `kv-<team>`. Роли действуют на уровне команды и окружения; более тонкое ограничение (отдельные пути, время суток) вне рамок проекта.
