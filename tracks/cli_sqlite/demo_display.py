"""Rich terminal display for Cortex CLI Learning Demo."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

HINT_MARKER = "--- HINT from prior sessions ---"


def show_demo_header(task_id: str, model: str, sessions: int, domain: str) -> None:
    """Big banner with demo info."""
    info = Text()
    info.append("Task: ", style="dim")
    info.append(f"{task_id}", style="bold white")
    info.append("  Model: ", style="dim")
    info.append(f"{model}", style="bold white")
    info.append("  Sessions: ", style="dim")
    info.append(f"{sessions}", style="bold white")
    info.append("  Domain: ", style="dim")
    info.append(f"{domain}", style="bold white")

    panel = Panel(
        info,
        title="[bold cyan]CORTEX CLI LEARNING DEMO[/bold cyan]",
        subtitle="[dim]Can an LLM teach itself a tool it's never seen?[/dim]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def show_system_prompt(prompt: str) -> None:
    """Display exact system prompt shown to executor model."""
    console.print(
        Panel(
            prompt.strip() or "(empty system prompt)",
            title="[bold blue]SYSTEM PROMPT[/bold blue]",
            border_style="blue",
            padding=(1, 1),
        )
    )


def show_loaded_lessons(lessons_text: str, lessons_loaded: int) -> None:
    """Display the literal lessons injected into runtime prompt."""
    if lessons_loaded <= 0:
        return
    console.print(
        Panel(
            lessons_text.strip() or "(no lesson text)",
            title=f"[bold yellow]LESSONS INJECTED ({lessons_loaded})[/bold yellow]",
            border_style="yellow",
            padding=(1, 1),
        )
    )


def show_session_header(run_num: int, total_runs: int, session_id: int, lessons_loaded: int) -> None:
    """Session start banner."""
    header = Text()
    header.append(f"Run {run_num}/{total_runs}", style="bold cyan")
    header.append("  |  ", style="dim")
    header.append(f"Session {session_id}", style="white")
    header.append("  |  ", style="dim")
    if lessons_loaded > 0:
        header.append(f"{lessons_loaded} lessons loaded", style="yellow")
    else:
        header.append("no prior lessons", style="dim")

    console.print()
    console.rule(header)


def show_step(step: int, tool_name: str, ok: bool, error: str | None) -> None:
    """Real-time step indicator per tool call."""
    line = Text()
    line.append(f"  Step {step}: ", style="dim")
    line.append(f"{tool_name} ", style="bold white")
    if ok:
        line.append("OK", style="bold green")
    else:
        line.append("ERR ", style="bold red")
        if error:
            short = error[:120].replace("\n", " ")
            if len(error) > 120:
                short += "..."
            line.append(short, style="red")
    console.print(line)


def show_agent_thinking(text: str) -> None:
    """Render assistant reasoning with no truncation."""
    console.print(
        Panel(
            text.strip(),
            title="[dim]AGENT THINKING[/dim]",
            border_style="grey54",
            style="dim",
            padding=(0, 1),
        )
    )


def show_hint_injection(error_text: str, hint_text: str) -> None:
    """Render original error plus injected prior-session hints."""
    content = Text()
    content.append("Base error:\n", style="bold red")
    content.append((error_text or "").strip() + "\n\n", style="red")
    content.append("Injected hint block:\n", style="bold yellow")
    content.append((hint_text or "").strip(), style="yellow")
    console.print(
        Panel(
            content,
            title="[bold yellow]HINT INJECTION[/bold yellow]",
            border_style="bright_yellow",
            padding=(0, 1),
        )
    )


def _flatten_tool_result(content: Any) -> str:
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict)]
        return " ".join(parts)
    if isinstance(content, str):
        return content
    return str(content)


def show_session_replay(messages: list[dict], detail: str = "compact") -> None:
    """Walk message list and display agent activity."""
    if detail == "none":
        return

    console.print()
    console.print("  [dim]--- Agent Replay ---[/dim]")

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")

            if btype == "text" and detail == "full" and role == "assistant":
                text = (block.get("text") or "").strip()
                if text:
                    show_agent_thinking(text)

            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                inp_short = str(inp)[:140]
                if len(str(inp)) > 140:
                    inp_short += "..."
                console.print(f"    [cyan][TOOL][/cyan] {name} [dim]{inp_short}[/dim]")

            elif btype == "tool_result":
                is_err = block.get("is_error", False)
                result_text = _flatten_tool_result(block.get("content", ""))
                if is_err and detail == "full" and HINT_MARKER in result_text:
                    base, hint = result_text.split(HINT_MARKER, 1)
                    show_hint_injection(base.strip(), HINT_MARKER + hint)
                else:
                    short = result_text[:160].replace("\n", " ")
                    if len(result_text) > 160:
                        short += "..."
                    if is_err:
                        console.print(f"    [red][RESULT][/red] ERROR: {short}")
                    else:
                        console.print(f"    [green][RESULT][/green] {short}")

    console.print("  [dim]--------------------[/dim]")


def show_session_score(score: float, passed: bool, reasons: list[str] | str | None) -> None:
    """Bold score display."""
    label = Text(f"{'PASS' if passed else 'FAIL'} {score:.2f}", style="bold green" if passed else "bold red")
    reason_text = ""
    if isinstance(reasons, list) and reasons:
        reason_text = "; ".join(str(r) for r in reasons[:3])
    elif isinstance(reasons, str) and reasons:
        reason_text = reasons

    content = Text()
    content.append_text(label)
    if reason_text:
        content.append(f"\n{reason_text}", style="dim")

    panel = Panel(content, border_style="green" if passed else "red", padding=(0, 1))
    console.print(panel)


def _category_style(category: str) -> str:
    lowered = category.lower()
    if lowered in {"negative", "mistake"}:
        return "bold red"
    if lowered == "shortcut":
        return "bold green"
    return "bold cyan"


def show_critic_output(
    raw_lessons: list[dict[str, Any]] | None,
    filtered_lessons: list[dict[str, Any]] | None,
    rejected_lessons: list[dict[str, Any]] | None,
) -> None:
    """Display critic proposal and quality-filter result."""
    raw_lessons = raw_lessons or []
    filtered_lessons = filtered_lessons or []
    rejected_lessons = rejected_lessons or []
    if not raw_lessons and not filtered_lessons and not rejected_lessons:
        return

    table = Table(show_header=True, header_style="bold white", border_style="magenta")
    table.add_column("Set", width=9)
    table.add_column("Category", width=12)
    table.add_column("Lesson")
    table.add_column("Steps", width=10)

    def _add_rows(label: str, lessons: list[dict[str, Any]]) -> None:
        for lesson in lessons:
            category = str(lesson.get("category", ""))
            text = str(lesson.get("lesson", ""))
            steps = ",".join(str(step) for step in lesson.get("evidence_steps", []))
            table.add_row(
                label,
                Text(category, style=_category_style(category)),
                text,
                steps or "-",
            )

    _add_rows("raw", raw_lessons)
    _add_rows("kept", filtered_lessons)
    _add_rows("reject", rejected_lessons)
    console.print(
        Panel(
            table,
            title=(
                f"[bold magenta]CRITIC OUTPUT[/bold magenta] "
                f"[dim](raw={len(raw_lessons)}, kept={len(filtered_lessons)}, reject={len(rejected_lessons)})[/dim]"
            ),
            border_style="magenta",
            padding=(0, 1),
        )
    )


def show_judge_reasoning(reasons: list[str] | str | None, critique: str | None) -> None:
    """Display judge reasoning payload from metrics."""
    reason_lines: list[str] = []
    if isinstance(reasons, list):
        reason_lines = [str(item) for item in reasons if str(item).strip()]
    elif isinstance(reasons, str) and reasons.strip():
        reason_lines = [reasons.strip()]

    content = Text()
    if reason_lines:
        content.append("Reasons:\n", style="bold magenta")
        for line in reason_lines:
            content.append(f"- {line}\n", style="magenta")
    if critique and critique.strip():
        content.append("\nRaw judge output:\n", style="bold dim")
        content.append(critique.strip(), style="dim")
    if not reason_lines and not (critique and critique.strip()):
        content.append("(no judge reasoning captured)", style="dim")

    console.print(
        Panel(
            content,
            title="[bold magenta]JUDGE REASONING[/bold magenta]",
            border_style="magenta",
            padding=(0, 1),
        )
    )


def show_lessons_generated(count: int) -> None:
    """Lesson generation summary."""
    if count > 0:
        console.print(f"  [yellow]LESSONS GENERATED: {count}[/yellow]")
    else:
        console.print("  [dim]LESSONS GENERATED: 0[/dim]")


def show_learning_progress(scores: list[float]) -> None:
    """Score trajectory so far."""
    if not scores:
        return
    parts = Text()
    parts.append("  Progress: ", style="dim")
    for i, s in enumerate(scores):
        if s >= 0.9:
            style = "bold green"
        elif s >= 0.5:
            style = "yellow"
        else:
            style = "red"
        parts.append(f"{s:.2f}", style=style)
        if i < len(scores) - 1:
            parts.append(" -> ", style="dim")
    console.print(parts)


def show_final_summary(results: list[dict]) -> None:
    """Final summary table."""
    console.print()

    table = Table(
        title="Learning Curve Results",
        border_style="cyan",
        show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("Run", justify="center", style="bold", width=4)
    table.add_column("Session", justify="center", width=8)
    table.add_column("Score", justify="center", width=7)
    table.add_column("Result", justify="center", width=6)
    table.add_column("Steps", justify="center", width=6)
    table.add_column("Errors", justify="center", width=6)
    table.add_column("Lessons In", justify="center", width=10)
    table.add_column("Lessons Out", justify="center", width=11)
    table.add_column("Time", justify="right", width=7)

    for row in results:
        score = row.get("score", 0)
        passed = row.get("passed", False)
        score_style = "bold green" if score >= 0.9 else ("yellow" if score >= 0.5 else "red")
        result_text = Text("PASS", style="bold green") if passed else Text("FAIL", style="bold red")
        bar_width = 5
        filled = round(score * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        table.add_row(
            str(row.get("run", "")),
            str(row.get("session_id", "")),
            Text(f"{bar} {score:.2f}", style=score_style),
            result_text,
            str(row.get("steps", 0)),
            str(row.get("tool_errors", 0)),
            str(row.get("lessons_loaded", 0)),
            str(row.get("lessons_generated", 0)),
            f"{row.get('elapsed_s', 0):.1f}s",
        )

    console.print(table)

