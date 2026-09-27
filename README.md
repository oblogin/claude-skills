# claude-skills

Личный маркетплейс плагинов и скиллов для [Claude Code](https://claude.com/claude-code).
Здесь хранятся все мои скиллы: после переустановки Windows или Claude Code их можно вернуть за пару команд.

## Плагины

| Плагин | Скиллы | Что делает |
|---|---|---|
| `media` | `media:image-gen` | Генерирует картинки (иллюстрации, стикеры, иконки, фоны, прозрачные PNG) через Codex CLI и кладёт их в подходящую папку проекта |

## Восстановление на новой машине

В Claude Code:

```
/plugin marketplace add oblogin/claude-skills
/plugin install media@claude-skills
```

Или из терминала:

```bash
claude plugin marketplace add oblogin/claude-skills
claude plugin install media@claude-skills
```

Обновить после изменений в репозитории: `/plugin marketplace update claude-skills`.

### Что нужно для `media:image-gen`

- [Codex CLI](https://github.com/openai/codex) в `PATH`, вход выполнен (`codex login`), включена функция `image_generation`.
- Python 3 с библиотеками `pillow` и `numpy`: `python -m pip install pillow numpy`.

## Разработка

Рабочая копия лежит в `C:\AI\claude-skills` и подключена к Claude Code как локальный маркетплейс:

```bash
claude plugin marketplace add C:\AI\claude-skills
claude plugin install media@claude-skills
```

После правок поднимите `version` в `plugins/<плагин>/.claude-plugin/plugin.json`,
выполните `claude plugin marketplace update claude-skills` и перезапустите сессию.

## Как добавить новый скилл

- **В существующий плагин:** создайте `plugins/<плагин>/skills/<скилл>/SKILL.md`.
- **Новым плагином:**
  1. Создайте `plugins/<новый>/.claude-plugin/plugin.json` и `plugins/<новый>/skills/<скилл>/SKILL.md`.
  2. Добавьте запись в `.claude-plugin/marketplace.json`.

Скрипты скилла кладите рядом с ним (`skills/<скилл>/scripts/`). В `SKILL.md` ссылайтесь на них через базовую папку скилла, а не через `~/.claude/...`: плагины устанавливаются в кэш.
