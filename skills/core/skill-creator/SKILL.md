---
name: skill-creator
description: Use when creating or updating local skills under skills/; enforces SKILL.md folder format, valid frontmatter, and trigger-focused descriptions.
---

# Skill Creator (Local)

Use this when adding or updating skills under `skills/`.

## Required format

- One folder per skill.
- Each skill must live at `skills/<domain>/<skill-name>/SKILL.md`.
- `SKILL.md` must start with YAML frontmatter:
  - `name`
  - `description`
- Keep body concise and procedural.

## Rules

1. Metadata-first routing:
   - `name` and `description` should clearly state when the skill applies.
2. Progressive disclosure:
   - Keep SKILL body focused.
   - Put deep references in separate files only when needed.
3. Stable references:
   - Do not rename skill folders casually; `skill_ref` derives from folder path.
4. Updates:
   - Prefer patching existing skills over creating duplicates.

## Minimal template

```markdown
---
name: your-skill-name
description: What this skill does and when to use it.
---

# Skill Title

Short purpose.

## Steps
1. ...
2. ...
```
