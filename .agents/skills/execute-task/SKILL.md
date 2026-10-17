---
name: execute-task
description: Executes tasks specified in .agents/current_task.md with strict scope discipline, verification, and automatic git commit + push.
---

# Execute Task Skill

Use this skill to implement instructions formulated in `.agents/current_task.md`.

## Workflow:
1. **Read Task Definition:** Open and read `.agents/current_task.md` to get the context, objectives, modified files, and implementation details.
2. **Strict Scope & System Safety Discipline (Zero Scope Creep):**
   - Modify or create ONLY the project files specified in the task inside `/home/dofi/Dev/Aliparser`.
   - **STRICTLY FORBIDDEN:** Never run system package managers or privilege escalation commands (`sudo`, `pkexec`, `apt`, `apt-get`, `dpkg`, `snap`, `flatpak`) or install anything into the host OS. Only use project-local `venv/bin/python` and `venv/bin/pip`.
   - Do not refactor unrelated code.
3. **Verification:**
   - Run tests, type checks, or verification commands specified in `.agents/current_task.md` using `venv/bin/python`.
   - Ensure changes run without syntax errors or runtime exceptions.
4. **Automatic Git Commit & Push:**
   - Automatically execute the git commit and push command specified in `.agents/current_task.md` via terminal (`git add . && git commit -m "..." && git push origin main`).
   - Verify that `git status` is clean and changes are pushed to `origin/main`.
5. **Report:**
   - Summarize modified files, verification logs, and confirm the commit hash pushed to GitHub.
