"""Rich terminal display for Cortex CLI Learning Demo."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


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
        line.append("✓", style="bold green")
    else:
        line.append("✗ ", style="bold red")
        if error:
            # Truncate long errors for display
            short = error[:120].replace("\n", " ")
            if len(error) > 120:
                short += "..."
            line.append(short, style="red")
    console.print(line)


def show_session_replay(messages: list[dict], detail: str = "compact") -> None:
    """Walk the messages list and display agent activity.

    detail: 'compact' = tool calls only, 'full' = reasoning + tools, 'none' = skip
    """
    if detail == "none":
        return

    console.print()
    console.print("  [dim]─── Agent Replay ───[/dim]")

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
                    short = text[:200].replace("\n", " ")
                    if len(text) > 200:
                        short += "..."
                    console.print(f"    [dim italic]💭 {short}[/dim italic]")

            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                inp_short = str(inp)[:100]
                if len(str(inp)) > 100:
                    inp_short += "..."
                console.print(f"    [cyan]🔧 {name}[/cyan] [dim]{inp_short}[/dim]")

            elif btype == "tool_result":
                is_err = block.get("is_error", False)
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    parts = [b.get("text", "") for b in result_content if isinstance(b, dict)]
                    result_text = " ".join(parts)
                elif isinstance(result_content, str):
                    result_text = result_content
                else:
                    result_text = str(result_content)
                short = result_text[:120].replace("\n", " ")
                if len(result_text) > 120:
                    short += "..."
                if is_err:
                    console.print(f"    [red]  ↳ ERROR: {short}[/red]")
                else:
                    console.print(f"    [green]  ↳ {short}[/green]")

    console.print("  [dim]───────────────────[/dim]")


def show_session_score(score: float, passed: bool, reasons: list[str] | str | None) -> None:
    """Bold score display."""
    if passed:
        label = Text(f"PASS {score:.2f}", style="bold green")
    else:
        label = Text(f"FAIL {score:.2f}", style="bold red")

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


def show_lessons_generated(count: int) -> None:
    """Lesson generation summary."""
    if count > 0:
        console.print(f"  [yellow]📝 {count} lesson{'s' if count != 1 else ''} generated[/yellow]")
    else:
        console.print("  [dim]📝 no new lessons[/dim]")


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
            parts.append(" → ", style="dim")
    console.print(parts)


def show_final_summary(results: list[dict]) -> None:
    """Final summary table."""
    console.print()

    # Build table
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

    for r in results:
        score = r.get("score", 0)
        passed = r.get("passed", False)
        score_style = "bold green" if score >= 0.9 else ("yellow" if score >= 0.5 else "red")
        result_text = Text("PASS", style="bold green") if passed else Text("FAIL", style="bold red")

        # Visual bar for score
        bar_width = 5
        filled = round(score * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)

        table.add_row(
            str(r.get("run", "")),
            str(r.get("session_id", "")),
            Text(f"{bar} {score:.2f}", style=score_style),
            result_text,
            str(r.get("steps", 0)),
            str(r.get("tool_errors", 0)),
            str(r.get("lessons_loaded", 0)),
            str(r.get("lessons_generated", 0)),
            f"{r.get('elapsed_s', 0):.1f}s",
        )

    console.print(table)

    # Summary stats
    scores = [r.get("score", 0) for r in results]
    steps_list = [r.get("steps", 0) for r in results]
    errors_list = [r.get("tool_errors", 0) for r in results]
    total_lessons = sum(r.get("lessons_generated", 0) for r in results)
    passes = [i + 1 for i, r in enumerate(results) if r.get("passed")]

    console.print()
    stats = Text()

    # Score trajectory
    stats.append("Score trajectory: ", style="dim")
    for i, s in enumerate(scores):
        style = "bold green" if s >= 0.9 else ("yellow" if s >= 0.5 else "red")
        stats.append(f"{s:.2f}", style=style)
        if i < len(scores) - 1:
            stats.append(" → ", style="dim")
    stats.append("\n")

    # Total lessons
    stats.append(f"Total lessons accumulated: ", style="dim")
    stats.append(f"{total_lessons}", style="yellow")
    stats.append("\n")

    # Steps trend
    if len(steps_list) >= 2:
        delta_steps = steps_list[-1] - steps_list[0]
        trend = "↓ improving" if delta_steps < 0 else ("→ stable" if delta_steps == 0 else "↑ more steps")
        trend_style = "green" if delta_steps < 0 else ("dim" if delta_steps == 0 else "yellow")
        stats.append(f"Steps trend: {steps_list[0]} → {steps_list[-1]} ", style="dim")
        stats.append(f"({trend})", style=trend_style)
        stats.append("\n")

    # Errors trend
    if len(errors_list) >= 2:
        delta_errs = errors_list[-1] - errors_list[0]
        trend = "↓ fewer errors" if delta_errs < 0 else ("→ stable" if delta_errs == 0 else "↑ more errors")
        trend_style = "green" if delta_errs < 0 else ("dim" if delta_errs == 0 else "red")
        stats.append(f"Error trend: {errors_list[0]} → {errors_list[-1]} ", style="dim")
        stats.append(f"({trend})", style=trend_style)
        stats.append("\n")

    # Mastery
    if passes:
        stats.append(f"First perfect score: Run {passes[0]}", style="bold green")
        if len(passes) == len(results):
            stats.append(" (all runs passed!)", style="green")
    else:
        stats.append("No passing runs yet", style="red")
    stats.append("\n")

    # Learning speed
    if len(scores) >= 2:
        improvement = scores[-1] - scores[0]
        if improvement > 0.3:
            speed = "Fast learner! 🚀"
            style = "bold green"
        elif improvement > 0:
            speed = "Steady progress 📈"
            style = "yellow"
        elif improvement == 0:
            speed = "Plateaued"
            style = "dim"
        else:
            speed = "Regression detected"
            style = "red"
        stats.append(f"Learning: ", style="dim")
        stats.append(speed, style=style)

    panel = Panel(stats, title="[bold cyan]Summary[/bold cyan]", border_style="cyan", padding=(1, 2))
    console.print(panel)
    console.print()
